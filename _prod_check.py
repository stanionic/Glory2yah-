import re
import time

import requests

BASE = 'https://glory2yah.onrender.com'
PSEUDO = '+50942882076'
PASSWORD = 'StanGlory2YahPub1986'
OUT = '_prod_check.txt'


def log(line):
    with open(OUT, 'a', encoding='utf-8') as fh:
        fh.write(line + '\n')


open(OUT, 'w', encoding='utf-8').close()

s = requests.Session()
s.headers['User-Agent'] = 'g2y-verify/1.0'


def csrf_of(html):
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html or '')
    return m.group(1) if m else None


# 1) login page
t0 = time.time()
r = s.get(BASE + '/admin/login', timeout=25)
log(f'[1] GET /admin/login -> {r.status_code} ({time.time()-t0:.1f}s)')
token = csrf_of(r.text)
log(f'    csrf_token found: {bool(token)}')

# 2) login
t0 = time.time()
r = s.post(BASE + '/admin/login',
           data={'pseudo': PSEUDO, 'password': PASSWORD, 'csrf_token': token or ''},
           timeout=25, allow_redirects=True)
log(f'[2] POST /admin/login -> {r.status_code} url={r.url} ({time.time()-t0:.1f}s)')
log(f'    logged_in(hlogin page absent): {"Admin Login" not in r.text and "konekte" not in r.text.lower()}')

# 3) admin alerts page -> WhatsApp status
t0 = time.time()
r = s.get(BASE + '/admin/alerts', timeout=25)
html = r.text
log(f'[3] GET /admin/alerts -> {r.status_code} ({time.time()-t0:.1f}s)')
log(f'    page_heading: {"Alèt Apwobasyon" in html}')
log(f'    pill_AKTIF: {"AKTIF" in html}')
log(f'    pill_PA_KONFIGIRE: {"PA KONFIGIRE" in html}')
log(f'    pill_DEZAKTIVE: {"DEZAKTIVE" in html}')
m = re.search(r'Founisè:\s*<b>([^<]+)</b>', html)
log(f'    provider: {m.group(1) if m else "n/a"}')
m = re.search(r'Nimewo:\s*<span[^>]*>([^<]+)</span>', html)
log(f'    number: {m.group(1) if m else "n/a"}')
m = re.search(r'Dènye voye:\s*([^<]+)<', html)
log(f'    last_provider: {m.group(1).strip() if m else "none yet"}')

# 4) fire a REAL test alert (WhatsApp + in-app)
test_token = csrf_of(html)
t0 = time.time()
r = s.post(BASE + '/admin/alerts/test',
           data={'csrf_token': test_token or ''}, timeout=40, allow_redirects=False)
log(f'[4] POST /admin/alerts/test -> {r.status_code} ({time.time()-t0:.1f}s)')

# 5) re-read page to see the "last sent" provider
time.sleep(2)
r = s.get(BASE + '/admin/alerts', timeout=25)
html = r.text
m = re.search(r'Dènye voye:\s*([^<]+)<', html)
log(f'[5] after test -> Dènye voye: {m.group(1).strip() if m else "none (send failed/not delivered)"}')

log('DONE')
