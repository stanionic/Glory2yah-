"""Comprehensive ADS fix verification"""
import os
import sys

os.environ['FLASK_ENV'] = 'development'
os.environ['RATELIMIT_ENABLED'] = '0'

# Use module-level app (single instance — avoids CSRF/file conflicts)
import app as app_module
from app import db
from app.models.ad import Ad
from app.models.user import User
from app.services.ad_service import AdService

app = app_module.app
PASS = 0
FAIL = 0

def check(name, cond, detail=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f'  [PASS] {name}')
    else:
        FAIL += 1
        print(f'  [FAIL] {name} {detail}')

with app.app_context():
    print('=' * 60)
    print('ADS FIX VERIFICATION')
    print('=' * 60)

    # ── TEST 1: category column exists after migration ──
    print('\n--- TEST 1: ads.category column exists ---')
    from sqlalchemy import inspect
    insp = inspect(db.engine)
    ad_cols = {c['name'] for c in insp.get_columns('ads')}
    check('category column present', 'category' in ad_cols, str(ad_cols))

    # ── TEST 2: Ad.to_dict() includes category ──
    print('\n--- TEST 2: to_dict() includes category ---')
    ad = Ad.query.first()
    if ad:
        d = ad.to_dict()
        check('category key in to_dict', 'category' in d, str(d.keys()))
        check('category value is string', isinstance(d.get('category'), str), repr(d.get('category')))
    else:
        check('category key in to_dict (no ads, skip)', True, 'no ad row')

    # ── TEST 3: AdService.create_ad validates ad_type ──
    print('\n--- TEST 3: ad_type validation ---')
    from app.utils.validators import ValidationError
    try:
        AdService.create_ad(
            user_whatsapp='+50999990000',
            title='Test Bad Type',
            description='This is a fairly long description for testing ad type validation here.',
            media_type='text',
            ad_type='garbage',
            price_gkach=0
        )
        check('invalid ad_type rejected', False, 'no exception raised')
    except ValidationError as e:
        # The validation DID fire — error message is in Haitian Creole
        # (contains "sell" / "publish" / "piblisite"), proving 'garbage' is rejected.
        msg = str(e).lower()
        check('invalid ad_type rejected', 'sell' in msg or 'publish' in msg or 'piblisite' in msg, str(e))
    except Exception as e:
        check('invalid ad_type rejected', False, f'wrong exception: {e}')

    # ── TEST 4: create_ad accepts valid category ──
    print('\n--- TEST 4: create_ad with valid category ---')
    test_ad = AdService.create_ad(
        user_whatsapp='+50999990000',
        title='Televizyon Samsung 55 pou vann',
        description='Nouvo televizyon Samsung 55 pous ak garanti. Pri negosyab, livrezon disponib.',
        media_type='images',
        images='test.jpg',
        ad_type='sell',
        price_gkach=500,
        category='electronics'
    )
    check('ad created', test_ad is not None)
    check('category stored', test_ad.category == 'electronics', repr(getattr(test_ad, 'category', None)))
    check('ad_type sell', test_ad.ad_type == 'sell', repr(test_ad.ad_type))
    test_ad.admin_status = 'approved'
    db.session.commit()

    # ── TEST 5: create_ad defaults invalid category to 'other' ──
    print('\n--- TEST 5: invalid category falls back to other ---')
    ad2 = AdService.create_ad(
        user_whatsapp='+50999990000',
        title='Bagay pou vann kategori envalid',
        description='Deskripsyon long ase pou pase validasyon minimòm karaktè yo.',
        media_type='text',
        ad_type='publish',
        price_gkach=0,
        category='not-a-category'
    )
    check('invalid category -> other', ad2.category == 'other', repr(ad2.category))
    db.session.delete(ad2)
    db.session.commit()

    # ── TEST 6: marketplace only shows sell ads (checked via API) ──
    print('\n--- TEST 6: marketplace filters ad_type=sell ---')
    client = app.test_client()
    r = client.get('/mache/api/products?per_page=50')
    data = r.get_json()
    check('api 200', r.status_code == 200, str(r.status_code))
    if data and data.get('success'):
        for p in data.get('products', [])[:10]:
            if p.get('ad_type') != 'sell':
                check('all products are sell', False, f"ad_type={p.get('ad_type')}")
                break
        else:
            check('all products are sell', True)
    else:
        check('all products are sell', False, f'no data: {data}')

    # ── TEST 7: category filter works ──
    print('\n--- TEST 7: category filter in marketplace ---')
    r = client.get('/mache/api/products?per_page=50&category=electronics')
    data = r.get_json()
    if data and data.get('success'):
        prods = data.get('products', [])
        check('electronics filter returns ads', len(prods) >= 1, f'got {len(prods)}')
        for p in prods:
            if p.get('category') != 'electronics':
                check('all results are electronics', False, repr(p.get('category')))
                break
        else:
            check('all results are electronics', True)
    else:
        check('electronics filter returns ads', False, f'no data: {data}')

    # ── TEST 8: marketplace index page renders (category all) ──
    print('\n--- TEST 8: marketplace index renders ---')
    r = client.get('/mache/?per_page=20')
    check('index 200', r.status_code == 200, str(r.status_code))
    check('page has product grid', 'products' in r.data.decode('utf-8', errors='replace') or 'card' in r.data.decode('utf-8', errors='replace'))

    # ── TEST 9: submit_ad page has category selector ──
    print('\n--- TEST 9: submit_ad category select ---')
    r = client.get('/submit_ad')
    body = r.data.decode('utf-8', errors='replace')
    check('category select present', 'name="category"' in body, 'no category select')
    check('electronics option present', 'value="electronics"' in body)

    # ── TEST 10: view_ad shows updated view count ──
    print('\n--- TEST 10: view_ad increments & shows count ---')
    before = test_ad.view_count
    r = client.get(f'/ad/{test_ad.ad_id}')
    check('view_ad 200', r.status_code == 200, str(r.status_code))
    db.session.refresh(test_ad)
    check('view_count incremented', test_ad.view_count == before + 1, f'{before} -> {test_ad.view_count}')

    # ── TEST 11: check_marketplace payment_status fix ──
    print('\n--- TEST 11: check_marketplace valid payment status ---')
    src = open('check_marketplace.py', encoding='utf-8').read()
    check("uses 'completed' not 'approved'", "payment_status = 'completed'" in src and "payment_status = 'approved'" not in src)

    # cleanup test ad
    db.session.delete(test_ad)
    db.session.commit()

    print('\n' + '=' * 60)
    print(f'RESULTS: {PASS} passed, {FAIL} failed')
    print('=' * 60)
    sys.exit(0 if FAIL == 0 else 1)