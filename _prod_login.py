import re
import time

import requests

BASE = 'https://glory2yah.onrender.com'
OUT = '_prod_login.txt'
open(OUT, 'w', encoding='utf-8').close()


def log(line):
    with open(OUT, 'a', encoding='utf-8') as fh:
        fh.write(line + '\n')


def csrf_of(html):
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html or '')
    return m.group(1) if m else None


candidates = [
    ('+50942882076', 'StanGlory2YahPub1986'),
    ('Admin509', 'StanGlory2YahPub1986'),
    ('+50942882076', 'StanGlory2YahPub1986'),
]

for pseudo, password in candidates:
    s = requests.Session()
    s.headers['User-Agent'] = 'g2y-verify/1.0'
    r = s.get(BASE + '/admin/login', timeout=25)
    token = csrf_of(r.text)
    r = s.post(BASE + '/admin/login',
               data={'pseudo': pseudo, 'password': password, 'csrf_token': token or ''},
               timeout=25, allow_redirects=False)
    loc = r.headers.get('Location', '')
    log(f'pseudo={pseudo!r}: POST /admin/login -> {r.status_code} Location={loc!r}')
    if r.status_code in (301, 302, 303, 307, 308):
        r2 = s.get(loc if loc.startswith('http') else BASE + loc, timeout=25, allow_redirects=False)
        log(f'    follow -> {r2.status_code} Location={r2.headers.get("Location","")!r}')
        if r2.status_code == 200:
            log(f'    has_admin_alerts_heading: {"Alèt Apwobasyon" in r2.text}')
        r3 = s.get(BASE + '/admin/alerts', timeout=25, allow_redirects=False)
        log(f'    GET /admin/alerts -> {r3.status_code} Location={r3.headers.get("Location","")!r}')
        if r3.status_code == 200:
            log(f'    -> AKTIF={"AKTIF" in r3.text} PA_KONFIGIRE={"PA KONFIGIRE" in r3.text} '
                f'DEZAKTIVE={"DEZAKTIVE" in r3.text}')
            m = re.search(r'Founisè:\s*<b>([^<]+)</b>', r3.text)
            log(f'    -> provider={m.group(1) if m else "n/a"}')
        break
    else:
        low = r.text.lower()
        log(f'    invalid_hint={"envalid" in low} not_admin_hint={"administrateur" in low}')
