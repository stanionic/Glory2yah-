"""Adapter registry, config loading (no secrets in files) and router inventory."""
import json
import re

from .base import Capability, RouterAuthError, RouterError, UnsupportedOperation
from .mikrotik import MikroTikAdapter
from .openwrt import OpenWrtAdapter
from .unsupported import (AsusAdapter, DLinkAdapter, GenericAdapter, TendaAdapter,
                          TPLinkAdapter)

ADAPTERS = {c.kind: c for c in (OpenWrtAdapter, MikroTikAdapter, TPLinkAdapter, TendaAdapter,
                                DLinkAdapter, AsusAdapter, GenericAdapter)}
_REF = re.compile(r'^[A-Za-z0-9_\-]{1,40}$')


def create_adapter(kind, host, username=None, password=None, **kw):
    cls = ADAPTERS.get(kind)
    if cls is None:
        raise ValueError(f'unknown router kind: {kind}')
    if cls in (OpenWrtAdapter, MikroTikAdapter):
        return cls(host, username, password, **kw)
    return cls(host)


def discover(host, http):
    """Best-effort, NON-invasive fingerprint (no logins, no credential guessing).
    Returns 'openwrt', 'mikrotik' or 'generic'. Heuristic: confirm with identify()."""
    try:
        s, raw = http('POST', f'https://{host}/ubus', {'Content-Type': 'application/json'},
                      json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'list',
                                  'params': ['0' * 32, '*']}).encode())
        if s in (200, 401, 403) and b'jsonrpc' in (raw or b''):
            return 'openwrt'
    except Exception:
        pass
    try:
        s, raw = http('GET', f'https://{host}/rest/system/resource', {}, None)
        if s == 401:
            return 'mikrotik'
    except Exception:
        pass
    return 'generic'


def load_routers(config, environ, http_factory=None):
    """config: list of {ref, kind, host, username, password_env, port?, scheme?, verify_tls?}

    Passwords come ONLY from environment variables named by ``password_env``;
    a literal ``password`` key is refused so secrets never sit in config files.
    Returns (adapters_by_ref, errors_by_ref). One bad entry never blocks the rest.
    """
    adapters, errors = {}, {}
    for entry in config or []:
        ref = str(entry.get('ref', ''))
        try:
            if not _REF.match(ref):
                raise ValueError('invalid ref')
            if ref in adapters:
                raise ValueError('duplicate ref')
            if 'password' in entry:
                raise RouterAuthError('inline "password" refused: use password_env')
            kw = {k: entry[k] for k in ('port', 'scheme', 'verify_tls', 'ca_file') if k in entry}
            if http_factory:
                kw['http'] = http_factory(entry)
            pw = environ.get(entry.get('password_env', '')) if entry.get('password_env') else None
            kind = entry.get('kind', 'generic')
            if kind in ('openwrt', 'mikrotik') and not pw:
                raise RouterAuthError(f'environment variable {entry.get("password_env")!r} is not set')
            adapters[ref] = create_adapter(kind, entry.get('host'), entry.get('username'), pw, **kw)
        except Exception as e:
            errors[ref or '?'] = str(e)[:200]
    return adapters, errors


def inventory(adapters, errors=None):
    """Snapshot sent to the cloud. Contains NO credentials, only identity/capabilities."""
    out = []
    for ref, ad in adapters.items():
        item = {'ref': ref, 'kind': ad.kind, 'vendor': ad.vendor_label,
                'support_level': ad.support_level, 'hardware_verified': bool(ad.hardware_verified),
                'status': 'UNSUPPORTED' if ad.support_level == 'unsupported' else 'OFFLINE',
                'model': '', 'firmware': '', 'capabilities': []}
        try:
            info = ad.identify()
            item.update(model=info.model, firmware=info.firmware)
            item['capabilities'] = sorted(c.value for c in ad.capabilities(refresh=True))
            if ad.support_level != 'unsupported':
                item['status'] = 'ONLINE'
        except (RouterError, UnsupportedOperation) as e:
            item['error'] = str(e)[:160]
        except Exception as e:                      # unexpected: report, never crash the agent
            item['error'] = f'{type(e).__name__}'
        out.append(item)
    for ref, msg in (errors or {}).items():
        out.append({'ref': ref, 'kind': 'invalid', 'vendor': '', 'support_level': 'unsupported',
                    'hardware_verified': False, 'status': 'OFFLINE', 'model': '',
                    'firmware': '', 'capabilities': [], 'error': msg})
    return out
