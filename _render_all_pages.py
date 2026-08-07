import sys, os, re, json, time
sys.path.insert(0, os.getcwd())
import logging
for _n in ('app','werkzeug','flask_limiter'):
    try: logging.getLogger(_n).setLevel(logging.CRITICAL)
    except: pass
from app import create_app
app = create_app()
c = app.test_client()
os.makedirs('_dbg_pages', exist_ok=True)

pages = {
    'index.html': ('/', None),
    'mache.html': ('/mache/', None),
    'mache_lot.html': ('/mache/?category=other', None),
    'mache_prix_bawo.html': ('/mache/?sort=price_low', None),
    'mache_prix_wo.html': ('/mache/?sort=price_high', None),
    'mache_popile.html': ('/mache/?sort=popular', None),
}
import threading, urllib.parse
for out, (path, qs) in pages.items():
    r = c.get(path, follow_redirects=True)
    print(f"{path} -> {r.status_code} bytes={len(r.data)}", file=sys.stderr)
    html_bytes = r.data
    # Rewrite relative static/css/js src to work in this server - prefix with /__static/ proxy
    html = html_bytes.decode('utf-8', errors='replace')
    html = html.replace('href="/static/', 'href="http://127.0.0.1:5001/__static/')
    html = html.replace('src="/static/', 'src="http://127.0.0.1:5001/__static/')
    html = html.replace("url('/static/", "url('http://127.0.0.1:5001/__static/")
    with open('_dbg_pages/'+out, 'w', encoding='utf-8') as f:
        f.write(html)

# NDJSON logs
from collections import Counter
ndjson = []
def add(h, m, d):
    ndjson.append({'sessionId':'marketplace-approved-ads-empty-state','runId':'post','hypothesisId':h,
                   'location':'render_all_pages.py','msg':'[DEBUG] '+m,'data':d,'ts':int(time.time()*1000)+len(ndjson)})
r_m = c.get('/mache/', follow_redirects=True)
html_m = r_m.get_data(as_text=True)
add('A','GET /mache/ exit success full HTML snapshot (post-fix)', {
    'status': r_m.status_code, 'bytes': len(r_m.data),
    'pwodui_count': re.search(r'(\d+) pwodui', html_m).group(1) if re.search(r'(\d+) pwodui', html_m) else None,
    'empty_present': 'Pa gen pwodui' in html_m,
    'filter_chip_count': len(re.findall(r'filter-chip', html_m)),
    'product_card_count': len(re.findall(r'product-card', html_m)),
})
r_api = c.get('/mache/api/products?per_page=50')
j = json.loads(r_api.get_data(as_text=True))
products = j.get('products', [])
cnt_type = dict(Counter(p.get('ad_type') for p in products))
cnt_cat = dict(Counter(p.get('category') for p in products))
add('B','GET /mache/api/products post-fix per-type breakdown', {
    'status': r_api.status_code, 'products_len': len(products),
    'per_ad_type': cnt_type, 'per_category': cnt_cat,
    'all_have_quantity_key': all('quantity' in p for p in products),
    'all_have_publish_fee_gkach': all('publish_fee_gkach' in p for p in products),
    'unique_ids_len': len(set(p.get('ad_id','?') for p in products)),
})
r_lot = c.get('/mache/?category=other', follow_redirects=True)
html_lot = r_lot.get_data(as_text=True)
add('E','GET /mache/?category=other (Lot chip) post-fix', {
    'status': r_lot.status_code, 'bytes': len(r_lot.data),
    'pwodui_count': re.search(r'(\d+) pwodui', html_lot).group(1) if re.search(r'(\d+) pwodui', html_lot) else None,
    'empty_present': 'Pa gen pwodui' in html_lot,
    'other_category_cnt': len([p for p in products if p.get('category')=='other']),
    'product_card_count': len(re.findall(r'product-card', html_lot)),
})
r_home = c.get('/', follow_redirects=True)
html_home = r_home.get_data(as_text=True)
add('C','GET / home page carousel + feed post-fix', {
    'status': r_home.status_code, 'bytes': len(r_home.data),
    'carousel_total_slides_last': re.findall(r'totalSlides[^<]*<span[^>]*>\s*(\d+)', html_home)[-1:] if re.findall(r'totalSlides[^<]*<span[^>]*>\s*(\d+)', html_home) else [],
    'product_card_count': len(re.findall(r'product-card', html_home)),
})
os.makedirs('.dbg', exist_ok=True)
with open('.dbg/trae-debug-log-marketplace-approved-ads-empty-state.ndjson','a',encoding='utf-8') as f:
    for line in ndjson: f.write(json.dumps(line)+'\n')
with open('_dbg_pages/_api_summary.json','w',encoding='utf-8') as f:
    json.dump({'products_len': len(products), 'per_type': cnt_type, 'per_category': cnt_cat,
               'all_have_quantity_key': all('quantity' in p for p in products),
               'all_have_publish_fee_gkach': all('publish_fee_gkach' in p for p in products),
               'unique_ids_len': len(set(p.get('ad_id','?') for p in products)),
              }, f, indent=2)
print("DONE", file=sys.stderr)
