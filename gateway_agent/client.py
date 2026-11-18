"""Signed, outbound-only HTTP client for the cloud management API."""
import base64
import hashlib
import json
import secrets
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse


class CloudUnreachable(Exception):
    """Network-level failure: the gateway must keep working offline."""


class CloudRejected(Exception):
    def __init__(self, status, message):
        super().__init__(f'{status}: {message}')
        self.status = status


class UrllibTransport:
    def __init__(self, timeout=10, allow_insecure=False):
        self.timeout, self.allow_insecure = timeout, allow_insecure

    def request(self, method, url, headers, body):
        if not url.startswith('https://') and not self.allow_insecure:
            raise CloudRejected(0, 'refusing non-HTTPS cloud URL')
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            raise CloudUnreachable(str(e))


def canonical(method, path, ts, nonce, body):
    return '\n'.join([method.upper(), path, str(ts), nonce,
                      hashlib.sha256(body).hexdigest()]).encode()


class CloudClient:
    def __init__(self, base_url, private_key, gateway_uid=None, transport=None,
                 now_fn=time.time, nonce_fn=lambda: secrets.token_urlsafe(18)):
        self.base_url = base_url.rstrip('/')
        self.key, self.gateway_uid = private_key, gateway_uid
        self.transport, self.now_fn, self.nonce_fn = transport or UrllibTransport(), now_fn, nonce_fn

    def sign_headers(self, method, path, body):
        ts, nonce = int(self.now_fn()), self.nonce_fn()
        sig = self.key.sign(canonical(method, path, ts, nonce, body))
        return {'Content-Type': 'application/json', 'X-UWZ-Gateway': self.gateway_uid,
                'X-UWZ-Timestamp': str(ts), 'X-UWZ-Nonce': nonce,
                'X-UWZ-Signature': base64.b64encode(sig).decode()}

    def _call(self, path, payload, signed=True):
        body = json.dumps(payload, separators=(',', ':')).encode()
        headers = self.sign_headers('POST', path, body) if signed else {
            'Content-Type': 'application/json'}
        status, raw = self.transport.request('POST', self.base_url + path, headers, body)
        try:
            data = json.loads(raw or b'{}')
        except ValueError:
            data = {}
        if status >= 400:
            raise CloudRejected(status, data.get('error', 'request failed'))
        return data

    def enroll(self, token, public_key_b64, agent_version):
        return self._call('/wifi/gateway/enroll', {
            'token': token, 'public_key': public_key_b64,
            'agent_version': agent_version}, signed=False)

    def heartbeat(self, portal_url=None, clock=None):
        body = {}
        if portal_url:
            body['portal_url'] = portal_url
        if clock:
            body['clock'] = clock
        return self._call('/wifi/gateway/heartbeat', body)

    def sync_policy(self, cursor=0):
        return self._call('/wifi/gateway/sync-policy', {'cursor': cursor})

    def report_routers(self, routers):
        return self._call('/wifi/gateway/routers', {'routers': routers})

    def sync(self, events):
        return self._call('/wifi/gateway/sync', {'events': events})
