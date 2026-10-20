import re
import time

import requests

BASE = 'https://glory2yah.onrender.com'
OUT = '_prod_login2.txt'
open(OUT, 'w', encoding='utf-8').close()


def log(line):
    with open(OUT, 'a', encoding='utf-8') as fh:
        fh.write(str(line) + '\n')


def csrf_of(html):
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html or '')
    return m.group(1) if m else None


pseudos = ['Admin509', 'admin509', '+50942882076', '50942882076']
PASSWORD = 'StanGlory2YahPub1986'

winner = None
for p in pseudos:
    s = requests.Session()
    s.headers['User-Agent'] = 'g2y-verify/1.0'
    g = s.get(BASE + '/admin/login', timeout=25)
    token = csrf_of(g.text)
    r = s.post(BASE + '/admin/login',
               data={'pseudo': p, 'password': PASSWORD, 'csrf_token': token or ''},
               headers={'Referer': BASE + '/admin/login'},
               timeout=25, allow_redirects=False)
    loc = r.headers.get('Location', '')
    note = ''
    if r.status_code == 200:
        note = 'invalid' if 'envalid' in r.text.lower() else 're-render'
    log(f'pseudo={p!r}: {r.status_code} Location={loc!r} {note}')
    if r.status_code == 429:
        log('  RATE LIMITED - stopping')
        break
    if loc.rstrip('/').endswith('/admin') or loc == '/admin/':
        winner = (p, s)
        log('  >>> SUCCESS (redirected to admin dashboard)')
        break
    time.sleep(1)

if winner:
    p, s = winner
    a = s.get(BASE + '/admin/alerts', timeout=25)
    html = a.text
    log(f'GET /admin/alerts -> {a.status_code}')
    log(f'  heading_ok     : {"Alèt Apwobasyon" in html}')
    log(f'  pill_AKTIF     : {"AKTIF" in html}')
    log(f'  pill_PA_KONFIG : {"PA KONFIGIRE" in html}')
    log(f'  pill_DEZAKTIVE : {"DEZAKTIVE" in html}')
    m = re.search(r'Founisè:\s*<b>([^<]+)</b>', html)
    log(f'  provider       : {m.group(1) if m else "n/a"}')
    m = re.search(r'Nimewo:\s*<span[^>]*>([^<]+)</span>', html)
    log(f'  number         : {m.group(1) if m else "n/a"}')
    m = re.search(r'Dènye voye:\s*([^<]+)<', html)
    log(f'  last_provider  : {m.group(1).strip() if m else "none yet"}')
    # fire the REAL test alert
    tok = csrf_of(html)
    t0 = time.time()
    t = s.post(BASE + '/admin/alerts/test', data={'csrf_token': tok or ''},
               timeout=45, allow_redirects=False)
    log(f'POST /admin/alerts/test -> {t.status_code} ({time.time()-t0:.1f}s) '
        f'Location={t.headers.get("Location")!r}')
    time.sleep(3)
    a2 = s.get(BASE + '/admin/alerts', timeout=25)
    m = re.search(r'Dènye voye:\s*([^<]+)<', a2.text)
    log(f'AFTER test -> last_provider: {m.group(1).strip() if m else "none"}')
else:
    log('No pseudo worked with that password.')
