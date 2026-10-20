import time

import requests

urls = [
    'https://glory2yah.onrender.com/health',
    'https://glory2yah.net/health',
    'https://glory2yahpub.com/health',
]

with open('_probe.txt', 'w', encoding='utf-8') as fh:
    for u in urls:
        t0 = time.time()
        try:
            r = requests.get(u, timeout=20, allow_redirects=True)
            body = (r.text or '')[:160].replace('\n', ' ')
            line = f'{u} -> {r.status_code} | {body} | {time.time()-t0:.1f}s'
        except Exception as e:
            line = f'{u} -> FAIL {type(e).__name__}: {str(e)[:120]} | {time.time()-t0:.1f}s'
        fh.write(line + '\n')
        fh.flush()
