"""
Canonical public site URL - single source of truth for absolute links.

Anything that leaves the process as a *link* (Open Graph tags, share shortlinks,
WhatsApp/SMS message bodies, background workers) must resolve through here.

Why this exists
---------------
The resolution logic used to live as a private closure inside the
``url_for``/OG context processor in :mod:`app`, so it was unreachable from
``src/notifications.py`` and the alert services. Those callers therefore
hard-coded fallbacks - which is how ``https://yourdomain.com/...`` ended up in
WhatsApp messages sent to real sellers, and why links generated off a request
(threads, CLI scripts) pointed at ``http://localhost``.

Resolution order (first non-empty wins)
---------------------------------------
1. ``SITE_URL`` / ``PUBLIC_BASE_URL`` / ``BASE_URL`` from Flask *config*
2. The same names from the environment (config may not be built yet)
3. Current request host, honouring ``X-Forwarded-Proto`` / ``X-Forwarded-Host``
   (Render/Heroku terminate TLS in front of the app)
4. ``SERVER_NAME`` + ``PREFERRED_URL_SCHEME``
5. :data:`DEFAULT_SITE_URL`

Step 3 still resolves first-class for local development (``localhost:5000``),
so nothing needs an env var to work on a dev box; step 5 only kicks in when
there is genuinely no request and no configuration - the case where the previous
code produced a useless ``localhost`` link.
"""
import os

#: Production canonical origin. ``www`` is the host the domain actually serves.
DEFAULT_SITE_URL = 'https://www.glory2yah.net'

_ENV_KEYS = ('SITE_URL', 'PUBLIC_BASE_URL', 'BASE_URL')


def _trim(url):
    return (url or '').strip().rstrip('/')


def site_base_url():
    """Return the canonical origin, without a trailing slash. Never raises."""
    # 1. Flask config (set from env by app.config.Config)
    try:
        from flask import current_app
        if current_app and getattr(current_app, 'config', None):
            for key in _ENV_KEYS:
                val = _trim(current_app.config.get(key))
                if val:
                    return val
    except Exception:
        pass

    # 2. Environment (no app context yet: CLI scripts, workers, import time)
    for key in _ENV_KEYS:
        val = _trim(os.environ.get(key))
        if val:
            return val

    # 3. Live request host, behind the proxy headers Render sets
    try:
        from flask import request
        if request and request.environ:
            scheme = (request.headers.get('X-Forwarded-Proto')
                      or request.environ.get('wsgi.url_scheme')
                      or 'http').split(',')[0].strip()
            host = (request.headers.get('X-Forwarded-Host')
                    or request.host
                    or request.environ.get('HTTP_HOST')
                    or '').split(',')[0].strip()
            if host:
                return _trim(f'{scheme}://{host}')
    except Exception:
        pass

    # 4. Explicit SERVER_NAME
    try:
        from flask import current_app
        server_name = _trim(current_app.config.get('SERVER_NAME'))
        if server_name:
            scheme = current_app.config.get('PREFERRED_URL_SCHEME') or 'https'
            if not server_name.startswith(('http://', 'https://')):
                server_name = f'{scheme}://{server_name}'
            return _trim(server_name)
    except Exception:
        pass

    # 5. Last resort: the real production origin (never localhost - a localhost
    #    link handed to a WhatsApp message or an OG crawler is simply broken).
    return DEFAULT_SITE_URL


def absolute_url(path=''):
    """Join ``path`` onto the canonical origin. Absolute inputs pass through."""
    base = site_base_url()
    p = str(path or '').strip()
    if not p:
        return base
    if p.lower().startswith(('http://', 'https://')):
        return p.rstrip('/')
    return base + (p if p.startswith('/') else '/' + p)
