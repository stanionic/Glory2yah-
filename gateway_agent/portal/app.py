"""Local captive portal (WSGI). Works with NO internet: everything it needs is in
the local SQLite store, synchronised earlier from the cloud.

Security notes
* The device identity comes from the connection (REMOTE_ADDR -> ARP), never from
  a form field or header (X-Forwarded-For is ignored).
* All dynamic text (brand name, welcome text, package names) is HTML-escaped; the
  brand colour is re-validated; a strict CSP is sent; no cookies, no scripts.
* Invalid / unknown / used / expired / revoked codes all produce the SAME answer.
"""
import html
import json
import logging
import re
from urllib.parse import parse_qs, urlencode

from .access import AccessError

log = logging.getLogger('uwz.portal')
MAX_BODY = 4096
_COLOR = re.compile(r'^#[0-9A-Fa-f]{6}$')
HEADERS = [
    ('X-Content-Type-Options', 'nosniff'), ('X-Frame-Options', 'DENY'),
    ('Referrer-Policy', 'no-referrer'), ('Cache-Control', 'no-store'),
    ('Content-Security-Policy',
     "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
     "base-uri 'none'; frame-ancestors 'none'"),
]
MESSAGES = {
    'invalid': 'Kòd la pa valid, li ekspire oswa li deja itilize.',
    'unavailable': 'Sèvis la pa disponib pou kounye a. Tanpri kontakte responsab rezo a.',
    'not_ready': 'Sèvis la poko pare. Tanpri eseye ankò talè.',
    'device_limit': 'Kòd sa a rive nan limit aparèy li otorize.',
    'bad_device': 'Nou pa rekonèt aparèy ou. Rekonekte ou sou Wi-Fi a epi eseye ankò.',
    'disabled': 'Aksè gratis pa disponib.',
}


def _fmt_wait(seconds):
    m = max(1, -(-int(seconds) // 60))
    return f'{m} minit'


class PortalApp:
    def __init__(self, engine, access, resolver):
        self.engine, self.access, self.resolver = engine, access, resolver

    # ---------------------------------------------------------------- WSGI
    def __call__(self, environ, start_response):
        method, path = environ.get('REQUEST_METHOD', 'GET'), environ.get('PATH_INFO', '/')
        ip = environ.get('REMOTE_ADDR', '')                  # never X-Forwarded-For (spoofable)
        try:
            mac = self.resolver.resolve(ip)
        except Exception:
            mac = None
        try:
            if path == '/health':
                return self._json(start_response, 200, {'ok': True})
            if path == '/' and method == 'GET':
                return self._page(start_response, 200, self._home_for(mac, ))
            if path in ('/redeem', '/free', '/status', '/ticket'):
                want = 'GET' if path == '/status' else 'POST'
                if method != want:
                    return self._page(start_response, 405, self._home_for(mac, 'Metòd pa otorize.'),
                                      [('Allow', want)])
                if mac is None:
                    return self._page(start_response, 400, self._home_for(mac, MESSAGES['bad_device']))
                if path == '/status':
                    return self._json(start_response, 200, self._status(mac))
                form = self._form(environ)
                if form is None:
                    return self._page(start_response, 413, self._home_for(mac, 'Demann twò gwo.'))
                if path == '/redeem':
                    return self._grant_response(start_response, self.engine.redeem(
                        (form.get('code') or [''])[0], mac), mac, ip)
                if path == '/ticket':
                    return self._grant_response(start_response, self.engine.redeem_ticket(
                        (form.get('ticket') or [''])[0], mac), mac, ip)
                return self._grant_response(start_response, self.engine.free_access(mac), mac, ip)
            return self._page(start_response, 404, self._home_for(mac, 'Paj sa a pa egziste.'))
        except Exception:
            log.exception('portal error')
            return self._page(start_response, 500, self._home_for(mac, 'Erè entèn. Eseye ankò.'))

    # ------------------------------------------------------------- helpers
    def _form(self, environ):
        try:
            n = int(environ.get('CONTENT_LENGTH') or 0)
        except ValueError:
            return None
        if n < 0 or n > MAX_BODY:
            return None
        raw = environ['wsgi.input'].read(n).decode('utf-8', 'replace') if n else ''
        return parse_qs(raw, keep_blank_values=True, max_num_fields=10)

    def _grant_response(self, start_response, res, mac, ip):
        if res.ok:
            try:
                self.access.authorize(mac, ip, res.grant)
            except AccessError:
                log.exception('authorize failed')
                return self._page(start_response, 503, self._home_for(mac, 
                    'Kòd la bon men nou pa t ka ouvri aksè a. Antre kòd la ankò.'))
            g = res.grant
            return self._page(start_response, 200, self._success(g))
        if res.reason in ('locked', 'cooldown'):
            msg = f'Twòp esè. Tann {_fmt_wait(res.retry_after or 60)} epi eseye ankò.'
            return self._page(start_response, 429, self._home_for(mac, msg),
                              [('Retry-After', str(res.retry_after or 60))])
        status = {'invalid': 400, 'bad_device': 400, 'device_limit': 409, 'disabled': 404}.get(res.reason, 503)
        return self._page(start_response, status, self._home_for(mac, MESSAGES.get(res.reason, MESSAGES['invalid'])))

    def _status(self, mac):
        g = self.engine.status(mac)
        return {'active': bool(g), 'seconds_remaining': g['seconds_remaining'] if g else 0,
                'package': g['package'] if g else None,
                'data_mb': g['data_mb'] if g else None}

    # ---------------------------------------------------------------- views
    def _brand(self):
        portal = self.engine.store.get('portal') or {}
        vendor = self.engine.store.get('vendor') or {}
        color = portal.get('brand_color', '')
        return {'name': str(portal.get('brand_name') or vendor.get('name') or 'GLORY2YAH WIFI')[:60],
                'color': color if _COLOR.match(str(color)) else '#0b6b3a',
                'welcome': str(portal.get('welcome_text') or '')[:240],
                'voucher': portal.get('voucher_enabled', True),
                'free': bool(portal.get('free_access_enabled'))}

    def _layout(self, body, b):
        e = html.escape
        return ('<!doctype html><html lang="ht"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                f'<title>{e(b["name"])}</title><style>'
                'body{font-family:system-ui,sans-serif;margin:0;background:#f4f6f5;color:#1b1b1b}'
                f'header{{background:{b["color"]};color:#fff;padding:18px;text-align:center}}'
                'main{max-width:420px;margin:auto;padding:16px}'
                '.card{background:#fff;border-radius:10px;padding:16px;margin-bottom:14px}'
                f'button{{background:{b["color"]};color:#fff;border:0;border-radius:8px;'
                'padding:12px;width:100%;font-size:16px}'
                'input{width:100%;box-sizing:border-box;padding:12px;font-size:18px;'
                'border:1px solid #bbb;border-radius:8px;margin-bottom:10px;text-transform:uppercase}'
                '.msg{background:#fff3cd;padding:10px;border-radius:8px;margin-bottom:12px}'
                '.ok{background:#d1e7dd}li{margin:4px 0}'
                f'</style></head><body><header><h1>{e(b["name"])}</h1></header>'
                f'<main>{body}</main></body></html>')

    def _home_for(self, mac, message=None, cls='msg'):
        return self._home(message, cls, mac)

    def _buy_card(self, mac):
        """Paid packages are bought on Glory2YahPub (the customer's password never
        reaches this gateway). Shown only when the cloud is reachable and selling."""
        st, e = self.engine.store, html.escape
        base = st.get('cloud_base_url')
        ok_epoch, gw_uid = st.get('last_cloud_ok_epoch'), st.get('gateway_uid')
        tag = self.engine.tag_for(mac) if mac else None
        fresh = ok_epoch is not None and self.engine.now() - ok_epoch <= 600
        if not (base and str(base).startswith('https://') and gw_uid and tag and fresh
                and self.engine.can_sell()):
            return ''
        rows = []
        for p in self.engine.packages():
            if p['price_gkach'] > 0:
                url = f"{base}/wifi/buy?" + urlencode({'gw': gw_uid, 'pkg': p['id'], 'd': tag})
                rows.append(f'<li><a href="{e(url, quote=True)}">{e(p["name"])} · '
                            f'{self._dur(p["duration_minutes"])} · {p["price_gkach"]} Gkach</a></li>')
        if not rows:
            return ''
        return ('<div class="card"><strong>Achte ak Gkach</strong>'
                f'<ul>{"".join(rows)}</ul></div>')

    def _home(self, message=None, cls='msg', mac=None):
        b, e = self._brand(), html.escape
        parts = []
        if message:
            parts.append(f'<div class="{cls}">{e(message)}</div>')
        if b['welcome']:
            parts.append(f'<p>{e(b["welcome"])}</p>')
        if b['voucher']:
            parts.append('<div class="card"><form method="post" action="/redeem">'
                         '<label for="c">Antre kòd vouchè ou</label>'
                         '<input id="c" name="code" maxlength="20" autocomplete="off" '
                         'autocapitalize="characters" placeholder="XXXX-XXXX-XXXX" required>'
                         '<button type="submit">Konekte</button></form></div>')
        if b['free']:
            parts.append('<div class="card"><form method="post" action="/free">'
                         '<button type="submit">Aksè gratis</button></form></div>')
        parts.append(self._buy_card(mac))
        pk = self.engine.packages()
        if pk:
            items = ''.join(
                f'<li>{e(p["name"])}: {self._dur(p["duration_minutes"])}'
                f'{" · " + str(p["price_gkach"]) + " Gkach" if p["price_gkach"] else " · Gratis"}</li>'
                for p in pk)
            parts.append(f'<div class="card"><strong>Fòfè disponib</strong><ul>{items}</ul></div>')
        return self._layout(''.join(parts), b)

    @staticmethod
    def _dur(minutes):
        if minutes % 1440 == 0:
            return f'{minutes // 1440} jou'
        if minutes % 60 == 0:
            return f'{minutes // 60} èdtan'
        return f'{minutes} minit'

    def _success(self, g):
        b = self._brand()
        mins = g['seconds_remaining'] // 60
        msg = f'Ou konekte! Tan ki rete: {mins // 60} èdtan {mins % 60} minit.'
        return self._layout(f'<div class="msg ok">{html.escape(msg)}</div>', b)

    # --------------------------------------------------------------- output
    def _page(self, start_response, status, body, extra=()):
        data = body.encode('utf-8')
        start_response(f'{status} {_REASON.get(status, "")}'.strip(),
                       [('Content-Type', 'text/html; charset=utf-8'),
                        ('Content-Length', str(len(data)))] + HEADERS + list(extra))
        return [data]

    def _json(self, start_response, status, obj):
        data = json.dumps(obj).encode()
        start_response(f'{status} {_REASON.get(status, "")}'.strip(),
                       [('Content-Type', 'application/json'),
                        ('Content-Length', str(len(data)))] + HEADERS)
        return [data]


_REASON = {200: 'OK', 400: 'Bad Request', 404: 'Not Found', 405: 'Method Not Allowed',
           409: 'Conflict', 413: 'Payload Too Large', 429: 'Too Many Requests',
           500: 'Internal Server Error', 503: 'Service Unavailable'}
