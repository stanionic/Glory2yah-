import re

import requests

BASE = 'https://glory2yah.onrender.com'
OUT = '_prod_dbg.txt'
open(OUT, 'w', encoding='utf-8').close()


def log(line):
    with open(OUT, 'a', encoding='utf-8') as fh:
        fh.write(str(line) + '\n')


def csrf_of(html):
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html or '')
    return m.group(1) if m else None


s = requests.Session()
s.headers['User-Agent'] = 'Mozilla/5.0 (g2y-verify)'

r = s.get(BASE + '/admin/login', timeout=25)
log(f'GET /admin/login -> {r.status_code}')
log(f'  Set-Cookie header: {r.headers.get("Set-Cookie")}')
log(f'  session cookies  : {dict(s.cookies)}')
token = csrf_of(r.text)
log(f'  token preview    : {(token or "")[:16]}... (len={len(token or "")})')

r2 = s.post(BASE + '/admin/login',
            data={'pseudo': '+50942882076',
                  'password': 'StanGlory2YahPub1986',
                  'csrf_token': token or ''},
            headers={'Referer': BASE + '/admin/login'},
            timeout=25, allow_redirects=False)
log(f'POST /admin/login -> {r2.status_code} Location={r2.headers.get("Location")!r}')
log(f'  cookies after    : {dict(s.cookies)}')
log(f'  body snippet     : {re.sub(r"<[^>]+>", " ", r2.text)[:300]!r}')
