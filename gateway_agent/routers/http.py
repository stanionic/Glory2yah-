"""HTTP transport for router APIs (LAN side). TLS verification is ON by default."""
import ssl
import urllib.error
import urllib.request

from .base import RouterConnectionError


def build_ssl_context(verify_tls=True, ca_file=None):
    if verify_tls:
        return ssl.create_default_context(cafile=ca_file)
    # Explicit opt-in only, for LAN routers with self-signed certificates.
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def make_http(verify_tls=True, ca_file=None, timeout=10):
    ctx = build_ssl_context(verify_tls, ca_file)

    def http(method, url, headers, body):
        req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
        try:
            kw = {'context': ctx} if url.startswith('https://') else {}
            with urllib.request.urlopen(req, timeout=timeout, **kw) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            raise RouterConnectionError(f'router unreachable: {type(e).__name__}')
    return http
