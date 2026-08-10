"""Test rapide OG tags ad_detail + /s/ shortlink.

Exit 0: all assertions PASS.
Exit 1: échec (traceback printé).
"""
from __future__ import annotations

import os, sys, tempfile, uuid, json, re

tmpdir = tempfile.mkdtemp(prefix='g2y_og_test_')
for k in ['TESTING','FLASK_ENV','SECRET_KEY','DATABASE_URL','WTF_CSRF_ENABLED',
          'SESSION_FILE_DIR','UPLOAD_FOLDER','LOG_DIR','SITE_URL']:
    os.environ.pop(k, None)

os.environ['TESTING'] = 'True'
os.environ['FLASK_ENV'] = 'testing'
os.environ['SECRET_KEY'] = 'og-secret-test'
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['WTF_CSRF_ENABLED'] = 'False'
os.environ['SESSION_FILE_DIR'] = tmpdir
os.environ['UPLOAD_FOLDER'] = tmpdir
os.environ['LOG_DIR'] = tmpdir
os.environ['SITE_URL'] = 'https://glory2yah.onrender.com'  # SITE_URL pour URLs absolues sans request context besoin

from app import create_app, db
app = create_app()
client = app.test_client()

with app.app_context():
    db.create_all()
    from app.models.ad import Ad
    from app.models.user import User
    from werkzeug.security import generate_password_hash

    # User vendeur
    u = User(name="Vendeur Tès", pseudo="og_vendeur", email="ogv@test.local",
             whatsapp="+50966660001", password_hash=generate_password_hash("pass1234"),
             is_active=True)
    db.session.add(u); db.session.flush()

    # 1) Ad "sell" avec images + prix
    AD_ID_A = str(uuid.uuid4())
    a = Ad(ad_id=AD_ID_A, user_whatsapp=u.whatsapp,
           title="Kay Villa 5 Pièces vue sur Mer (Carries)",
           description="Bèl villa 5 chanm, 3 twalèt, ak pisin. Peye 30% avant, lès ou ka peye pandan 60 mwa san enterè.",
           media_type="images",
           images="photo_villa1.jpg,photo_villa2_plan.jpg,photo_villa3_piscine.jpg",
           ad_type="sell", price_gkach=1250000, quantity=1, category='house',
           admin_status='approved', payment_status='paid')
    db.session.add(a)

    # 2) Ad "publish" (sans prix)
    AD_ID_B = str(uuid.uuid4())
    b = Ad(ad_id=AD_ID_B, user_whatsapp=u.whatsapp,
           title="Swich on Premye Komèsyal Ou sou Glory2Yah",
           description="Kreye piblisite pou janm li genyen plis kliyan.",
           media_type="images", images="", ad_type="publish", price_gkach=0,
           admin_status='approved')
    db.session.add(b)

    db.session.commit()


def _strip_ws(s: str) -> str:
    return re.sub(r'\s+', ' ', s).strip()


def test_detail_page_og_sell():
    """Test detail /ad/<ID> sell product : absolute og:image, product:price HTG present, og:type=product"""
    r = client.get(f'/ad/{AD_ID_A}', headers={'User-Agent': 'Mozilla/5.0 Firefox/128'})
    assert r.status_code == 200, f"status attendu 200, got {r.status_code}"
    html = r.get_data(as_text=True)

    def _meta(prop):
        m = re.search(r'<meta\s+(?:property|name)="' + re.escape(prop) + r'"\s+content="([^"]*)"', html, re.I)
        return m.group(1) if m else None

    assert _meta('og:title') and 'Kay Villa' in _meta('og:title'), f"og:title: {_meta('og:title')}"
    assert _meta('og:type') == 'product', f"og:type attendu 'product' got {_meta('og:type')}"
    img = _meta('og:image')
    assert img, "og:image missing"
    assert img.startswith('http'), f"og:image DOIT etre URL absolue (http). got: {img}"
    assert 'photo_villa1.jpg' in img, f"og:image doit contenir photo_villa1.jpg. got: {img}"
    assert _meta('og:image:secure_url') and _meta('og:image:secure_url').startswith('https'), "og:image:secure_url absente/invalide"
    assert _meta('product:price:currency') == 'HTG', f"product:price:currency HTG attendu: {_meta('product:price:currency')}"
    price = float(_meta('product:price:amount'))
    assert price > 100, f"product:price:amount invalide (1.2M HTG attendu) got: {price}"
    assert _meta('twitter:card') == 'summary_large_image', f"twitter:card {_meta('twitter:card')}"
    # Carousel 2e image
    n_images = len(re.findall(r'<meta\s+property="og:image"\s+content="([^"]*)"', html, re.I))
    assert n_images >= 3, f"3 images attendues (villa1..villa3 + ?), found: {n_images}"
    # Canonical link
    m = re.search(r'<link\s+rel="canonical"\s+href="([^"]+)"', html, re.I)
    assert m and AD_ID_A in m.group(1), f"canonical missing ou pas ad_id: {m and m.group(1)}"
    # Title du navigateur contient prez (HTG via format_htg)
    tm = re.search(r'<title>(.*?)</title>', html, re.S | re.I)
    assert tm, "Pas de balise <title>"
    # format_htg renvoie "X,XXX.XX HTG" donc "HTG" est dans le titre
    assert 'HTG' in _strip_ws(tm.group(1)), f"Titre doit contenir prix HTG. Title: {tm.group(1)!r}"
    print(f"[PASS] test_detail_page_og_sell — og:image={img}, price HTG={price}")


def test_shortlink_crawler_ua_sell():
    """Test /s/<ID> avec User-Agent facebookexternalhit (crawler) : og tags bien injectés."""
    r = client.get(f'/s/{AD_ID_A}',
                   headers={'User-Agent': 'facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)'})
    assert r.status_code == 200, f"shortlink crawler attendu 200, got {r.status_code}"
    html = r.get_data(as_text=True)

    def _meta(prop):
        m = re.search(r'<meta\s+(?:property|name)="' + re.escape(prop) + r'"\s+content="([^"]*)"', html, re.I)
        return m.group(1) if m else None

    assert _meta('og:type') == 'product'
    img = _meta('og:image')
    assert img and img.startswith('https://glory2yah.onrender.com'), f"shortlink og:image invalide: {img!r}"
    assert 'photo_villa1.jpg' in img
    assert _meta('product:price:currency') == 'HTG'
    assert float(_meta('product:price:amount')) > 100
    # redirect present in <meta refresh> + <script> location.replace
    assert 'http-equiv="refresh"' in html.lower() or "http-equiv='refresh'" in html.lower()
    assert 'location.replace' in html or 'location.replace' in html
    # <link rel=canonical pointe sur /ad/...
    m = re.search(r'<link\s+rel="canonical"\s+href="([^"]+)"', html, re.I)
    assert m and f'/ad/{AD_ID_A}' in m.group(1), f"canonical /ad/<id> manquant: {m and m.group(1)}"
    print(f"[PASS] test_shortlink_crawler_ua_sell — crawler UA -> full OG tags. og:image={img}")


def test_shortlink_browser_human_redirect():
    """shortlink /s/<ID> avec UA navigateur classique → page contient les tags mais code de redirect OK (HTTP 200 + meta-refresh)."""
    r = client.get(f'/s/{AD_ID_A}', headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36'})
    assert r.status_code == 200, f"human UA attendu 200 + redirect soft (pas 302 sinon crawlers cassent). got {r.status_code}"
    html = r.get_data(as_text=True)
    assert f'/ad/{AD_ID_A}' in html
    assert 'location.replace' in html
    print(f"[PASS] test_shortlink_browser_human_redirect — human UA: HTTP 200 + meta-refresh/JS redirect vers canonical.")


def test_detail_page_og_publish_no_price():
    """Ad publish (sans prix) : pas de product:price, og:type=article, fallback og:image logo du site."""
    r = client.get(f'/ad/{AD_ID_B}', headers={'User-Agent': 'Mozilla/5.0'})
    assert r.status_code == 200
    html = r.get_data(as_text=True)

    def _meta(prop):
        m = re.search(r'<meta\s+(?:property|name)="' + re.escape(prop) + r'"\s+content="([^"]*)"', html, re.I)
        return m.group(1) if m else None

    assert _meta('og:type') == 'article'
    # Pas d'images → fallback logo /static/images/logo.png en ABSOLU
    img = _meta('og:image')
    assert img and img.startswith('http'), f"publish fallback og:image doit etre absolue: {img!r}"
    assert 'logo.png' in img
    assert _meta('product:price:amount') is None or _meta('product:price:amount') == ""  # No price tag
    print(f"[PASS] test_detail_page_og_publish_no_price — og:image fallback={img}")


def test_regression_share_routes_regression_existing():
    """Régression: /s/b/<batch_id> toujours 302 (pas modifié)."""
    r = client.get('/s/b/batch_nonexistent')
    # Pas loggé → 401 redirect vers /auth/login (car @login_required)
    assert r.status_code in (302, 401) and '/auth/login' in (r.headers.get('Location','') or ''), f"batch_click auth protection doit exister: status={r.status_code} Location={r.headers.get('Location')}"
    print(f"[PASS] test_regression_share_routes_regression_existing — /s/b/.. still protected.")


try:
    test_detail_page_og_sell()
    test_shortlink_crawler_ua_sell()
    test_shortlink_browser_human_redirect()
    test_detail_page_og_publish_no_price()
    test_regression_share_routes_regression_existing()
    print("\n=== OG PREVIEW: 5/5 TESTS PASS ===")
    sys.exit(0)
except Exception:
    import traceback
    traceback.print_exc()
    sys.exit(1)
