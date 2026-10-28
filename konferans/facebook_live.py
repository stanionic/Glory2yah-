"""Facebook Live auto-publishing for KONFERANS (Meta Graph API).

Lets a room owner link a Facebook Page once (OAuth) and then start a live
straight from KONFERANS: we create the broadcast through the Graph API, read
back the ingest URL + stream key, and hand them to the existing server-side RTMP
relay (konferans/stream_relay.py). No OBS, no copy/paste of the key.

Everything is optional and env-driven (FACEBOOK_APP_ID / FACEBOOK_APP_SECRET).
When they are absent, is_configured() returns False and the manual RTMP path
keeps working untouched.

Privacy: the long-lived Page access token is stored ENCRYPTED at rest with a key
derived from SECRET_KEY. The raw stream key is NEVER stored — it is returned to
the owner's browser only, exactly like the manual flow.

Note: publishing to a Page requires a Meta App with App Review for
`pages_manage_posts` (+ `pages_read_engagement`), and the Page/account must meet
Meta's eligibility rules (account >= 60 days, Page >= 100 followers). Meta
returns explicit error codes for those two cases (see describe_error()).
"""
import base64
import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request

from flask import current_app

# Scopes needed to create and end a live video on a Page.
FACEBOOK_SCOPES = 'pages_show_list,pages_read_engagement,pages_manage_posts'

_TIMEOUT = 20  # seconds


class FacebookError(Exception):
    """A Graph API failure carrying a human (Creole) message for the owner."""

    def __init__(self, message, code=None, subcode=None, http_status=None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.subcode = subcode
        self.http_status = http_status


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
def _cfg(key, default=None):
    try:
        return current_app.config.get(key, default)
    except Exception:
        return default


def is_configured():
    """True when App ID + App Secret are present, i.e. auto-Live can be offered."""
    return bool(_cfg('FACEBOOK_ENABLED'))


def _graph_version():
    return (_cfg('FACEBOOK_GRAPH_VERSION') or 'v26.0').strip() or 'v26.0'


def _graph_base():
    return f"https://graph.facebook.com/{_graph_version()}"


# --------------------------------------------------------------------------- #
# Token encryption (Fernet, key derived from SECRET_KEY)
# --------------------------------------------------------------------------- #
def _fernet():
    """Build a Fernet instance from SECRET_KEY, or None if unavailable."""
    try:
        from cryptography.fernet import Fernet
    except Exception:
        return None
    secret = (_cfg('SECRET_KEY') or '')
    if not secret:
        return None
    digest = hashlib.sha256(f'konferans-fb::{secret}'.encode('utf-8')).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_token(raw):
    """Encrypt a sensitive token for storage. Returns None on failure."""
    if not raw:
        return None
    f = _fernet()
    if f is None:
        return None
    try:
        return f.encrypt(raw.encode('utf-8')).decode('ascii')
    except Exception:
        return None


def decrypt_token(enc):
    """Decrypt a stored token. Returns None on failure (e.g. key rotated)."""
    if not enc:
        return None
    f = _fernet()
    if f is None:
        return None
    try:
        return f.decrypt(enc.encode('ascii')).decode('utf-8')
    except Exception:
        return None


def encryption_available():
    """True when tokens can be encrypted (cryptography installed + SECRET_KEY set)."""
    return _fernet() is not None


# --------------------------------------------------------------------------- #
# Low-level Graph helpers (urllib — no `requests` dependency)
# --------------------------------------------------------------------------- #
def _read_json(resp):
    try:
        return json.loads(resp.read().decode('utf-8') or '{}')
    except Exception:
        return {}


def _raise_graph_error(payload, http_status=None):
    err = (payload or {}).get('error') or {}
    code = err.get('code')
    subcode = err.get('error_subcode')
    raise FacebookError(
        describe_error(code, subcode, err.get('message')),
        code=code, subcode=subcode, http_status=http_status,
    )


def _graph_get(path, params):
    url = f"{_graph_base()}/{path.lstrip('/')}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, method='GET')
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return _read_json(resp)
    except urllib.error.HTTPError as e:
        payload = _read_json(e)
        _raise_graph_error(payload, e.code)
    except FacebookError:
        raise
    except Exception as e:  # network / DNS / TLS
        raise FacebookError(f"Pa t kapab kominike ak Facebook: {e}")


def _graph_post(path, params):
    url = f"{_graph_base()}/{path.lstrip('/')}"
    data = urllib.parse.urlencode(params or {}).encode('utf-8')
    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return _read_json(resp)
    except urllib.error.HTTPError as e:
        payload = _read_json(e)
        _raise_graph_error(payload, e.code)
    except FacebookError:
        raise
    except Exception as e:
        raise FacebookError(f"Pa t kapab kominike ak Facebook: {e}")


def describe_error(code, subcode=None, raw=None):
    """Turn Meta error codes into an actionable Creole message."""
    if code == 190:
        return ("Token Facebook la pa valid oswa li ekspire. Rekonekte Facebook la "
                "nan KONFERANS.")
    if code == 1363120 or subcode == 1363120:
        return ("Kont Facebook oswa Paj ou a poko gen 60 jou. Meta pa pèmèt Live "
                "API sou kont ki twò jèn.")
    if code == 1363144 or subcode == 1363144:
        return ("Paj ou a poko rive 100 abòne. Meta egzije omwen 100 abòne pou "
                "Live API.")
    if code == 10 or code == 200:
        return ("Pèmisyon manke. App Meta a bezwen 'pages_manage_posts' epi "
                "pasè App Review.")
    if code == 368:
        return "Meta bloke kont lan tanporèman pou vyolasyon règ. Verifye Kontèl Kalite."
    if raw:
        return f"Facebook refize: {raw}"
    return "Facebook refize demann lan (erè enkoni)."


# --------------------------------------------------------------------------- #
# OAuth
# --------------------------------------------------------------------------- #
def oauth_dialog_url(redirect_uri, state):
    """URL of the Facebook consent dialog the owner must visit."""
    params = {
        'client_id': _cfg('FACEBOOK_APP_ID', ''),
        'redirect_uri': redirect_uri,
        'state': state,
        'scope': FACEBOOK_SCOPES,
        'response_type': 'code',
    }
    return f"https://www.facebook.com/{_graph_version()}/dialog/oauth?" + urllib.parse.urlencode(params)


def exchange_code(code, redirect_uri):
    """Exchange the OAuth `code` for a short-lived user access token."""
    data = _graph_get('oauth/access_token', {
        'client_id': _cfg('FACEBOOK_APP_ID', ''),
        'client_secret': _cfg('FACEBOOK_APP_SECRET', ''),
        'redirect_uri': redirect_uri,
        'code': code,
    })
    token = data.get('access_token')
    if not token:
        _raise_graph_error(data)
    return token


def extend_user_token(short_token):
    """Exchange a short-lived user token for a ~60-day long-lived one."""
    data = _graph_get('oauth/access_token', {
        'grant_type': 'fb_exchange_token',
        'client_id': _cfg('FACEBOOK_APP_ID', ''),
        'client_secret': _cfg('FACEBOOK_APP_SECRET', ''),
        'fb_exchange_token': short_token,
    })
    return data.get('access_token') or short_token


def list_pages(user_token):
    """Return the Pages the user manages, each with its own Page access token.

    Page tokens obtained from a long-lived user token do not expire, which is
    exactly what we want to store.
    """
    data = _graph_get('me/accounts', {
        'access_token': user_token,
        'fields': 'id,name,access_token',
        'limit': 100,
    })
    return data.get('data') or []


# --------------------------------------------------------------------------- #
# Live video lifecycle
# --------------------------------------------------------------------------- #
def create_live_video(page_id, page_token, title='', description=''):
    """Create a LIVE_NOW broadcast on a Page and return ingest details.

    Returns a dict: {live_id, ingest_url, stream_key, page_id}.
    The stream key is derived from the returned stream URL and is returned to
    the caller only — never persisted.
    """
    params = {
        'status': 'LIVE_NOW',
        'access_token': page_token,
    }
    if title:
        params['title'] = title[:254]
    if description:
        params['description'] = description[:5000]

    data = _graph_post(f'{page_id}/live_videos', params)
    secure_url = data.get('secure_stream_url') or ''
    plain_url = data.get('stream_url') or ''
    live_id = data.get('id')
    if not live_id or not (secure_url or plain_url):
        _raise_graph_error(data)

    # Prefer the RTMPS endpoint (required by Facebook since 2021).
    ingest_url, ingest_key = _split_ingest(secure_url or plain_url)
    if not ingest_url or not ingest_key:
        raise FacebookError("Facebook pa retounen yon Server URL/kle valid.")

    return {
        'live_id': str(live_id),
        'ingest_url': ingest_url,
        'stream_key': ingest_key,
        'page_id': str(page_id),
    }


def _split_ingest(stream_url):
    """Split a stream URL like 'rtmps://host:443/rtmp/KEY' into (server, key)."""
    if not stream_url:
        return None, None
    try:
        parsed = urllib.parse.urlsplit(stream_url)
        server = f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"
        # The stream key is appended after the final '/' of the path.
        key = stream_url.rstrip('/').rsplit('/', 1)[-1]
        return server, key
    except Exception:
        return None, None


def end_live_video(live_id, page_token):
    """End an ongoing broadcast. Best-effort: returns True/False, never raises."""
    if not live_id or not page_token:
        return False
    try:
        _graph_post(live_id, {'end_live_video': 'true', 'access_token': page_token})
        return True
    except Exception:
        return False
