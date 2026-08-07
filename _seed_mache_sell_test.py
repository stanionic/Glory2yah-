"""Test sell-ADS-only in MACHE after marketplace fix.

INSERTS:
  - AD-SELL-0001  : ad_type='sell',  admin_status='approved' (DOIT apparaître dans /mache/)
  - AD-PUB-0001   : ad_type='publish', admin_status='approved' (NE DOIT PAS apparaître dans /mache/)
  - AD-SELL-PEND01: ad_type='sell',  admin_status='under_review' (NE DOIT PAS apparaître)

THEN renders /mache/ via test_client + reports:
  - db counts: approved_sell, approved_publish, pending_sell
  - HTML parsed counts: 'AD-SELL-0001' present? 'AD-PUB-0001' present? product grid count
Writes: _dbg_pages/mache_sell_test.html + NDJSON log.
"""
import os, json, sys, time, threading
sys.path.insert(0, os.path.abspath('.'))
from app import create_app, db

_DBG = '.dbg/trae-debug-log-mache-sell-only.ndjson'
_DBG_LOCK = threading.Lock()
def _vlog(h, m, d=None, r='post', loc='_seed_mache_sell.py'):
    try:
        p = {'sessionId':'mache-sell-approved','runId':r,'hypothesisId':h,'location':loc,
             'msg':'[DEBUG] '+m,'data':d or {},'ts':int(time.time()*1000)}
        with _DBG_LOCK:
            os.makedirs('.dbg', exist_ok=True)
            with open(_DBG,'a',encoding='utf-8') as f:
                f.write(json.dumps(p)+'\n')
    except Exception: pass

app = create_app('development')
with app.app_context():
    try:
        db.create_all()
    except Exception as e:
        print(f'create_all warn: {e}')
    from app.models.ad import Ad
    from app.models.user import User

    u = User.query.filter_by(whatsapp='+50911111111').first()
    if not u:
        u = User(whatsapp='+50911111111', pseudo='UserTest', password_hash='pbkdf2:sha256:1000$xx')
        try: db.session.add(u); db.session.commit()
        except Exception: db.session.rollback()
    uid = u.whatsapp

    # --- SEED 3 ADS if missing ---
    seed_rows = [
        ('AD-SELL-0001',  '[VANN] Sabliye 3kg - Manje Ayisyen',
         'Sable kaseròl fre dirak soti jaden. Pakèt 3 kg pri solid. Livrezon Area Port-au-Prince disponib.',
         'food', 'sell', 'approved', 175, 20, 0, 'sable-3kg.jpg,sable-2.jpg,sable-3.jpg', None),
        ('AD-PUB-0001',   '[PIBLIYE] Nouvo Pak Inivèsite Bank G2Y',
         'Chak semenn nan Gwoup Facebook lan nou pataje Konesans sou Envestisman nan Lajan. Rejoindre nou!',
         'other', 'publish', 'approved', 0, 0, 0, '', None),
        ('AD-SELL-PEND01','[VANN-PENDING] Telefon Xiaomi Redmi 13',
         'Telefon neuf, 256GB, 12GB RAM. Pri negociab. Whatsapp +509....',
         'electronics', 'sell', 'under_review', 45000, 2, 0, 'xiaomi13-1.jpg,xiaomi13-2.jpg', None),
    ]
    for (aid, title, desc, cat, atype, astatus, priceHTG, qty, views, imgs, video) in seed_rows:
        existing = Ad.query.filter_by(ad_id=aid).first()
        if not existing:
            from app.utils.currency import htg_to_gkach as _cvt
            priceG = _cvt(priceHTG) if priceHTG and atype=='sell' else 0
            ad = Ad(ad_id=aid, user_whatsapp=uid, title=title, description=desc,
                    category=cat, ad_type=atype, media_type='images',
                    images=imgs, video=video, price_gkach=priceG,
                    quantity=qty, admin_status=astatus, payment_status='paid')
            try:
                db.session.add(ad); db.session.commit()
                _vlog('S1', f'INSERT seed {aid} atype={atype} astatus={astatus} priceG={priceG}',
                      {'ad_id':aid,'ad_type':atype,'status':astatus,'price_gkach':priceG,'qty':qty})
            except Exception as e:
                db.session.rollback()
                print(f'WARN insert {aid}: {e}')
        else:
            # ensure fields match spec
            changed = False
            if existing.ad_type != atype: existing.ad_type = atype; changed=True
            if existing.admin_status != astatus: existing.admin_status = astatus; changed=True
            if existing.payment_status != 'paid': existing.payment_status='paid'; changed=True
            if changed:
                try: db.session.commit(); _vlog('S1', f'UPDATED seed {aid}',{'ad_id':aid,'now_status':astatus,'now_type':atype})
                except Exception: db.session.rollback()
            else:
                _vlog('S1', f'Seed {aid} exists ok',{'ad_id':aid,'status':astatus,'type':atype})

    # --- DB COUNTS REPORT ---
    from app.models.ad import Ad
    cnt_all_approved   = Ad.query.filter_by(admin_status='approved').count() or 0
    cnt_sell_approved  = Ad.query.filter_by(admin_status='approved', ad_type='sell').count() or 0
    cnt_pub_approved   = Ad.query.filter_by(admin_status='approved', ad_type='publish').count() or 0
    cnt_sell_pending   = Ad.query.filter_by(admin_status='under_review', ad_type='sell').count() or 0
    _vlog('S2', 'DB counts after seed',
          {'all_approved':cnt_all_approved,'sell_approved':cnt_sell_approved,
           'publish_approved':cnt_pub_approved,'sell_under_review':cnt_sell_pending})

# --- Render /mache/ using test_client + parse output ---
client = app.test_client()
t0 = time.time()
resp = client.get('/mache/')
dt = int((time.time() - t0) * 1000)
html = resp.data.decode('utf-8', errors='replace')

os.makedirs('_dbg_pages', exist_ok=True)
outp = os.path.join('_dbg_pages','mache_sell_test.html')
with open(outp,'w',encoding='utf-8') as f:
    f.write(html)

import re
# quick parse: does AD-SELL-0001 / AD-PUB-0001 appear in the rendered HTML (within heading / product title)?
has_sell_approved    = 'AD-SELL-0001' in html or '[VANN] Sabliye 3kg' in html
has_publish_approved = 'AD-PUB-0001'  in html or '[PIBLIYE] Nouvo Pak Inivèsite' in html
has_sell_pending     = 'AD-SELL-PEND01' in html or '[VANN-PENDING] Telefon Xiaomi' in html
# count product card blocks or heading h3/h4s for 'VANN' vs 'PIBLIYE'
vann_count   = len(re.findall(r'\[VANN\]', html))
pub_count    = len(re.findall(r'\[PIBLIYE\]', html))
video_tag_ct = html.lower().count('<video')
product_tag  = html.count('product-card') + html.count('link product')

summary = {
    'path':'/mache/','status':resp.status_code,'bytes':len(resp.data),'ms':dt,
    'has_sell_approved_AD-SELL-0001_in_html': bool(has_sell_approved),
    'has_publish_approved_AD-PUB-0001_in_html': bool(has_publish_approved),
    'has_sell_pending_AD-SELL-PEND01_in_html': bool(has_sell_pending),
    '[VANN] heading count in html': vann_count,
    '[PIBLIYE] heading count in html': pub_count,
    'product_card_link_or_class_hits': product_tag,
    'video_tag_count': video_tag_ct,
}
print(json.dumps(summary, indent=2, ensure_ascii=False))
_vlog('S3', '/mache/ render counts after fix sell-only filter', summary)
with open('_dbg_pages/_mache_sell_summary.json','w',encoding='utf-8') as f:
    json.dump({'db':{'all_approved':cnt_all_approved,'sell_approved':cnt_sell_approved,
                     'publish_approved':cnt_pub_approved,'sell_pending':cnt_sell_pending},
               'render':summary}, f, indent=2, ensure_ascii=False)

# Final PASS/FAIL verdict
PASS = (bool(has_sell_approved) and not bool(has_publish_approved) and not bool(has_sell_pending))
_vlog('S4', 'FINAL VERDICT SELL-ONLY FILTER: ' + ('PASS' if PASS else 'FAIL'),
      {'PASS':PASS,
       'assertion':'sell-approved must be visible; publish-approved & sell-pending MUST be HIDDEN from mache'})
print('VERDICT:', 'PASS ✓' if PASS else 'FAIL ✗')
