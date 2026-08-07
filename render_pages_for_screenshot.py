"""Render /mache, /mache?category=other, / to .html files using test_client for screenshots."""
import sys, os, re, json
sys.path.insert(0, os.getcwd())
import logging
for _n in ('app','werkzeug','flask_limiter'):
    try: logging.getLogger(_n).setLevel(logging.CRITICAL)
    except: pass

from app import create_app
app = create_app()
c = app.test_client()
os.makedirs('.dbg_pages', exist_ok=True)

r = c.get('/mache/', follow_redirects=True)
print(f"/mache/ -> {r.status_code}, len={len(r.data)}", file=sys.stderr)
with open('.dbg_pages/mache_all.html', 'wb') as f: f.write(r.data)

r2 = c.get('/mache/?category=other', follow_redirects=True)
print(f"/mache/?category=other -> {r2.status_code}, len={len(r2.data)}", file=sys.stderr)
with open('.dbg_pages/mache_lot.html', 'wb') as f: f.write(r2.data)

r3 = c.get('/', follow_redirects=True)
print(f"/ -> {r3.status_code}, len={len(r3.data)}", file=sys.stderr)
with open('.dbg_pages/index_home.html', 'wb') as f: f.write(r3.data)

# Evidence summary NDJSON append
import time
ndjson = [
    {'sessionId':'marketplace-approved-ads-empty-state','runId':'post','hypothesisId':'A',
     'location':'render_pages.py','msg':'[DEBUG] /mache/ rendered static HTML; evidence before screenshot',
     'data':{'status':r.status_code,'len_bytes':len(r.data),
             'pwodui_count':re.search(r'(\d+) pwodui', r.get_data(as_text=True)).group(1) if re.search(r'(\d+) pwodui', r.get_data(as_text=True)) else None,
             'empty_present':('Pa gen pwodui' in r.get_data(as_text=True)),
             'product_card_count':len(re.findall(r'product-card', r.get_data(as_text=True)))},
     'ts':int(time.time()*1000)},
    {'sessionId':'marketplace-approved-ads-empty-state','runId':'post','hypothesisId':'E',
     'location':'render_pages.py','msg':'[DEBUG] /mache/?category=other (Lot chip) rendered',
     'data':{'status':r2.status_code,'len_bytes':len(r2.data),
             'pwodui_count':re.search(r'(\d+) pwodui', r2.get_data(as_text=True)).group(1) if re.search(r'(\d+) pwodui', r2.get_data(as_text=True)) else None,
             'empty_present':('Pa gen pwodui' in r2.get_data(as_text=True)),
             'product_card_count':len(re.findall(r'product-card', r2.get_data(as_text=True)))},
     'ts':int(time.time()*1000)+1},
    {'sessionId':'marketplace-approved-ads-empty-state','runId':'post','hypothesisId':'C',
     'location':'render_pages.py','msg':'[DEBUG] / homepage carousel + feed rendered',
     'data':{'status':r3.status_code,'len_bytes':len(r3.data),
             'slides':re.findall(r'totalSlides[^<]*<span[^>]*>\s*(\d+)', r3.get_data(as_text=True))[-1:] if re.findall(r'totalSlides[^<]*<span[^>]*>\s*(\d+)', r3.get_data(as_text=True)) else [],
             'product_card_count':len(re.findall(r'product-card', r3.get_data(as_text=True)))},
     'ts':int(time.time()*1000)+2},
]
os.makedirs('.dbg', exist_ok=True)
with open('.dbg/trae-debug-log-marketplace-approved-ads-empty-state.ndjson','a',encoding='utf-8') as f:
    for line in ndjson:
        f.write(json.dumps(line)+'\n')

# Also dump product listing for evidence
r4 = c.get('/mache/api/products?per_page=50')
j = json.loads(r4.get_data(as_text=True))
from collections import Counter
cnt = dict(Counter(p.get('ad_type') for p in j.get('products',[])))
with open('.dbg_pages/api_summary.json','w',encoding='utf-8') as f:
    json.dump({'products_len': len(j.get('products',[])), 'per_type': cnt,
               'success': j.get('success'),
               'each_has_quantity': all('quantity' in p for p in j.get('products',[])),
               'each_has_publish_fee_gkach': all('publish_fee_gkach' in p for p in j.get('products',[])),
               'each_has_category': all('category' in p for p in j.get('products',[])),
               'unique_ids_len': len(set(p.get('ad_id','?') for p in j.get('products',[]))),
              }, f, indent=2)
print("DONE pages in .dbg_pages/", file=sys.stderr)
