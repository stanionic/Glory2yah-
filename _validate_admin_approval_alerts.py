"""End-to-end validation for the ADMIN APPROVAL WhatsApp alerts.

Verifies that EVERY traffic requiring admin approval notifies the administrator
via WhatsApp (+50942882076 by default) AND creates an in-app admin notification:

  * new ad submitted            (AdService.create_ad)
  * ad edited → re-approval     (AdService.update_ad)
  * publication-fee proof       (main.upload_payment → wrapper)
  * GKACH recharge request      (gkach.request_gkach)
  * GKACH cash withdrawal       (gkach.withdraw)
  * MENNEN driver enrolment     (mennem.register_driver)
  * event organization signup   (events.landing)
  * bank loan application       (bank.loan_apply)
  * seller certification        (wrapper)

The real HTTP send is replaced by a capture function, and the provider chain is
exercised with fake providers, so NO network call is made.

Run:  python _validate_admin_approval_alerts.py
"""
import os
import sys
import types

# Console on Windows defaults to cp1252 → printing a WhatsApp body containing an
# emoji would raise UnicodeEncodeError and abort the run. Force UTF-8 (never fail
# the harness because of a character).
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

os.environ['FLASK_ENV'] = 'testing'
os.environ['RATELIMIT_ENABLED'] = '0'
os.environ.setdefault('ADMIN_WHATSAPP', '+50942882076')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.notification import Notification  # noqa: E402
from app.models.mennem_driver import MennemDriver  # noqa: E402
from app.services import notification_service as NS  # noqa: E402
import app.services.admin_approval_alerts as AAA  # noqa: E402

app = create_app('testing')

results = []


def check(name, ok, extra=''):
    results.append((name, bool(ok)))
    line = ('PASS' if ok else 'FAIL') + ' - ' + name
    if extra:
        line += ' | ' + str(extra)
    safe = line.encode('ascii', 'replace').decode('ascii').replace('\n', ' / ')
    print(safe)


# ── intercept the WhatsApp send (no real HTTP) ───────────────────────────────
CAPTURED = []


def _fake_alert_admin(message, throttle_seconds=0):
    CAPTURED.append(message)


AAA.alert_admin = _fake_alert_admin

ADMIN_WA = '+50942882076'
SELLER_WA = '+50955551111'
DRIVER_WA = '+50955552222'

print('=' * 74)
print('1) ADMIN NUMBER + PROVIDER CHAIN')
print('=' * 74)
check('admin number resolved to digits', NS._admin_whatsapp(True) == '50942882076',
      NS._admin_whatsapp(True))
check('admin number resolved to E.164', NS._admin_whatsapp(False) == ADMIN_WA,
      NS._admin_whatsapp(False))
check('DEFAULT_ADMIN_WHATSAPP is +50942882076',
      NS.DEFAULT_ADMIN_WHATSAPP == ADMIN_WA, NS.DEFAULT_ADMIN_WHATSAPP)

_saved_providers = NS._WHATSAPP_PROVIDERS
_seen = {}


def _rec_provider(phone, message, _req):
    _seen['phone'] = phone
    _seen['message'] = message
    return types.SimpleNamespace(status_code=200)


NS._WHATSAPP_PROVIDERS = (('rec', _rec_provider),)
check('provider chain returns the provider name', NS._send_whatsapp_alert('ping') == 'rec')
check('provider receives the admin digits-only number',
      _seen.get('phone') == '50942882076', _seen.get('phone'))
check('provider receives the message body', _seen.get('message') == 'ping')

NS._WHATSAPP_PROVIDERS = (
    ('unset', lambda p, m, r: None),
    ('down', lambda p, m, r: types.SimpleNamespace(status_code=500)),
    ('up', _rec_provider),
)
check('unconfigured providers are skipped, next one wins',
      NS._send_whatsapp_alert('ping2') == 'up')

NS._WHATSAPP_PROVIDERS = (('down', lambda p, m, r: types.SimpleNamespace(status_code=500)),)
check('all-failing chain returns None', NS._send_whatsapp_alert('ping3') is None)

NS._WHATSAPP_PROVIDERS = (('boom', lambda p, m, r: (_ for _ in ()).throw(RuntimeError('x'))),)
check('raising provider never propagates', NS._send_whatsapp_alert('ping4') is None)
NS._WHATSAPP_PROVIDERS = _saved_providers

status = NS.whatsapp_alert_status()
check('whatsapp_alert_status exposes the admin number',
      status.get('phone') == ADMIN_WA, status.get('phone'))
check('whatsapp_alert_status is enabled by default', status.get('enabled') is True)


print()
print('=' * 74)
print('2) TEST FIXTURES (admin + seller accounts)')
print('=' * 74)
with app.app_context():
    db.create_all()
    admin = User(name='Admin Alert', pseudo='AdminAlert', whatsapp=ADMIN_WA,
                 is_admin=True, is_active=True)
    admin.set_password('admin-pass-1')
    db.session.add(admin)
    seller = User(name='Seller Alert', pseudo='SellerAlert', whatsapp=SELLER_WA,
                  is_active=True)
    seller.set_password('seller-pass-1')
    db.session.add(seller)
    db.session.commit()
    admin_id = admin.id
    seller_id = seller.id
    # fund the seller wallet so the withdrawal flow can be exercised
    from app.services.gkach_service import GkachService
    GkachService.get_or_create_account(SELLER_WA)
    db.session.commit()
    GkachService.add_balance(SELLER_WA, 5000, 'Test funding', 'admin_credit_debit')
check('admin + seller created', admin_id and seller_id)


def admin_notifications(n_type=None):
    with app.app_context():
        q = Notification.query.filter_by(recipient_id=admin_id, category='admin')
        if n_type:
            q = q.filter_by(type=n_type)
        return q.count()


print()
print('=' * 74)
print('3) NEW AD SUBMITTED  ->  admin approval alert')
print('=' * 74)
CAPTURED.clear()
with app.app_context():
    from app.services.ad_service import AdService
    ad = AdService.create_ad(
        user_whatsapp=SELLER_WA,
        title='Test Alèt Admin',
        description='Deskripsyon konplè pou piblisite tès la.',
        media_type='images', ad_type='publish', category='other',
    )
    ad_id = ad.ad_id
check('create_ad raised a WhatsApp approval alert', len(CAPTURED) == 1, len(CAPTURED))
msg = CAPTURED[0] if CAPTURED else ''
check('message tagged [APWOBASYON] + PIBLISITE',
      '[APWOBASYON]' in msg and 'PIBLISITE' in msg, msg.replace('\n', ' / ')[:110])
check('message names the submitter', SELLER_WA in msg)
check('message names the ad title', 'Test Alèt Admin' in msg)
check('message links to the admin ads panel', '/admin/ads' in msg)
check('in-app admin notification (admin_new_ad) created',
      admin_notifications('admin_new_ad') == 1, admin_notifications('admin_new_ad'))

print()
print('=' * 74)
print('4) AD EDITED  ->  re-approval alert')
print('=' * 74)
CAPTURED.clear()
with app.app_context():
    AdService.update_ad(ad_id=ad_id, user_whatsapp=SELLER_WA,
                        title='Test Alèt Admin v2',
                        description='Deskripsyon modifye epi konplè pou tès la.')
check('update_ad raised a re-approval alert', len(CAPTURED) == 1, len(CAPTURED))
check('message says PIBLISITE MODIFYE',
      bool(CAPTURED) and 'PIBLISITE MODIFYE' in CAPTURED[0],
      (CAPTURED or [''])[0][:70])
check('in-app admin notification (admin_ad_edited) created',
      admin_notifications('admin_ad_edited') == 1, admin_notifications('admin_ad_edited'))


print()
print('=' * 74)
print('5) WRAPPERS: payment proof / recharge / withdrawal / driver / org / loan')
print('=' * 74)
CAPTURED.clear()
with app.app_context():
    from app.models.ad import Ad
    row = Ad.query.filter_by(ad_id=ad_id).first()
    AAA.alert_ad_payment_proof(row, filename='proof_test.jpg')
check('payment-proof alert', any('PREV PEMAN' in m for m in CAPTURED),
      (CAPTURED or [''])[0].replace('\n', ' / ')[:110])

CAPTURED.clear()
AAA.alert_recharge_request(SELLER_WA, 1000, request_id='req-1234',
                           currency='HTG', payment_method='moncash')
check('recharge alert carries amount + method',
      any('DEMANN RECHAJ GKACH' in m and '1000' in m and 'moncash' in m for m in CAPTURED),
      (CAPTURED or [''])[0].replace('\n', ' / ')[:110])

CAPTURED.clear()
AAA.alert_withdrawal_request(SELLER_WA, 1200, transaction_id='tx-999',
                             payment_method='moncash', payout_details='+50912345678')
check('withdrawal alert is marked URGENT',
      any('DEMANN RETRIZ' in m and '1200' in m for m in CAPTURED),
      (CAPTURED or [''])[0].replace('\n', ' / ')[:110])

CAPTURED.clear()
with app.app_context():
    driver = MennemDriver(name='Jean Test', whatsapp=DRIVER_WA, address='Delmas 33',
                          city='Delmas', base_fare=150, is_active=False,
                          is_verified=False)
    AAA.alert_driver_registration(driver)
check('driver registration alert',
      any('NOUVO CHOFE MENNEN' in m and 'Jean Test' in m for m in CAPTURED),
      (CAPTURED or [''])[0].replace('\n', ' / ')[:110])

CAPTURED.clear()
with app.app_context():
    from app.models.events import Event, EventOrganization
    ev = Event.query.filter_by(slug='sos-alo-legliz').first()
    org = EventOrganization(event_id=ev.id if ev else None,
                            org_name='Eglise Test', org_type='eglise',
                            phone='+50911111111', city='Port-au-Prince')
    AAA.alert_organization_registration(org, ev)
check('organization registration alert',
      any('NOUVO ORGANIZASYON' in m and 'Eglise Test' in m for m in CAPTURED),
      (CAPTURED or [''])[0].replace('\n', ' / ')[:110])

CAPTURED.clear()
with app.app_context():
    from app.models.bank import Loan, LoanProduct
    product = LoanProduct.query.first()
    loan = Loan(loan_id='loan-test-1', product_id=getattr(product, 'id', 1),
                user_id=seller_id, amount=3000, interest_amount=100,
                total_due=3100, status='pending', purpose='Boutik')
    seller_row = db.session.get(User, seller_id)
    AAA.alert_loan_request(loan, product, seller_row)
check('loan application alert contains the amount',
      any('DEMANN PRE' in m and '3000' in m for m in CAPTURED),
      (CAPTURED or [''])[0].replace('\n', ' / ')[:110])

CAPTURED.clear()
with app.app_context():
    AAA.alert_seller_certification(db.session.get(User, seller_id))
check('seller certification alert',
      any('SETIFIKASYON VANDE' in m for m in CAPTURED),
      (CAPTURED or [''])[0].replace('\n', ' / ')[:110])

CAPTURED.clear()
AAA.alert_approval_required('does-not-exist', actor='X', summary='Fallback test')
check('unknown kind falls back to the generic alert',
      any('APWOBASYON NESESE' in m for m in CAPTURED),
      (CAPTURED or [''])[0].replace('\n', ' / ')[:110])

# self-alert suppression: an admin submitting must not notify themselves
before = admin_notifications()
AAA.alert_approval_required('ad_new', actor=ADMIN_WA, summary='Pa admin',
                            entity_type='ad', entity_id='x-y-z', sender_id=admin_id)
check('admin who is the submitter is not self-alerted',
      admin_notifications() == before, f'{before} -> {admin_notifications()}')


print()
print('=' * 74)
print('6) LIVE HTTP FLOWS (test_client) — real routes, real wiring')
print('=' * 74)

anon = app.test_client()

# 6a. MENNEN driver registration
CAPTURED.clear()
r = anon.post('/mennenm/register_driver', data={
    'name': 'Chofe HTTP Test', 'phone': DRIVER_WA,
    'address': 'Delmas 33', 'price': '150',
}, follow_redirects=False)
with app.app_context():
    d_row = MennemDriver.query.filter_by(whatsapp=DRIVER_WA).first()
check('POST /mennenm/register_driver created the driver',
      r.status_code == 302 and d_row is not None, f'status={r.status_code}')
check('driver registration alerted the admin via WhatsApp',
      any('NOUVO CHOFE MENNEN' in m for m in CAPTURED),
      (CAPTURED or [''])[0].replace('\n', ' / ')[:110])
check('driver registration created an in-app admin notification',
      admin_notifications('admin_driver_registration') >= 1,
      admin_notifications('admin_driver_registration'))

# 6b. login as the seller, then request a GKACH cash withdrawal
seller_client = app.test_client()
seller_client.post('/auth/login', data={'identifier': SELLER_WA,
                                        'password': 'seller-pass-1'},
                   follow_redirects=True)
probe = seller_client.get('/gkach/withdraw')
check('seller is logged in (withdraw page reachable)',
      probe.status_code == 200, f'status={probe.status_code}')

CAPTURED.clear()
r = seller_client.post('/gkach/withdraw', data={
    'amount': '600', 'payment_method': 'moncash',
    'payout_details': '+50912345678', 'note': 'tès alèt',
}, follow_redirects=False)
check('POST /gkach/withdraw accepted', r.status_code in (302, 200), f'status={r.status_code}')
check('withdrawal alerted the admin via WhatsApp',
      any('DEMANN RETRIZ' in m and '600' in m for m in CAPTURED),
      (CAPTURED or [''])[0].replace('\n', ' / ')[:110])
check('withdrawal created an in-app admin notification',
      admin_notifications('admin_withdrawal_request') >= 1,
      admin_notifications('admin_withdrawal_request'))

# 6c. GKACH recharge request
CAPTURED.clear()
r = seller_client.post('/gkach/request', data={
    'amount': '1500', 'currency': 'HTG', 'payment_method': 'moncash',
}, follow_redirects=False)
check('POST /gkach/request accepted', r.status_code in (302, 200), f'status={r.status_code}')
check('recharge request alerted the admin via WhatsApp',
      any('DEMANN RECHAJ GKACH' in m and '1500' in m for m in CAPTURED),
      (CAPTURED or [''])[0].replace('\n', ' / ')[:110])

# 6d. Bank loan application
with app.app_context():
    from app.models.bank import LoanProduct
    if LoanProduct.query.count() == 0:
        db.session.add(LoanProduct(name='Prè Tès', min_amount=1000, max_amount=50000,
                                   interest_rate=5.0, duration_days=90, is_active=True))
        db.session.commit()
    product_id = LoanProduct.query.first().id
CAPTURED.clear()
r = seller_client.post(f'/bank/loans/apply/{product_id}', data={
    'amount': '5000', 'purpose': 'Boutik tès',
}, follow_redirects=False)
check('POST /bank/loans/apply accepted', r.status_code in (302, 200), f'status={r.status_code}')
check('loan application alerted the admin via WhatsApp',
      any('DEMANN PRE' in m and '5000' in m for m in CAPTURED),
      (CAPTURED or [''])[0].replace('\n', ' / ')[:110])

# 6e. Event organization registration (public form)
CAPTURED.clear()
r = anon.post('/events/sos-alo-legliz', data={
    'form_type': 'organization', 'org_type': 'eglise',
    'org_name': 'Eglise HTTP Test', 'contact_name': 'Pastè Test',
    'phone': '+50922223333', 'city': 'Delmas',
}, follow_redirects=False)
check('POST /events/sos-alo-legliz (organization) accepted',
      r.status_code in (302, 200), f'status={r.status_code}')
check('organization signup alerted the admin via WhatsApp',
      any('NOUVO ORGANIZASYON' in m for m in CAPTURED),
      (CAPTURED or [''])[0].replace('\n', ' / ')[:110])

# 6f. Owner edits an ad → re-approval alert on the real route
CAPTURED.clear()
r = seller_client.post(f'/auth/ads/{ad_id}/edit', data={
    'title': 'Test Alèt Admin v3',
    'description': 'Deskripsyon twazyèm vèsyon konplè pou tès la.',
}, follow_redirects=False)
check('POST /auth/ads/<id>/edit accepted', r.status_code in (302, 200),
      f'status={r.status_code}')
check('ad edit via HTTP alerted the admin',
      any('PIBLISITE MODIFYE' in m for m in CAPTURED),
      (CAPTURED or [''])[0].replace('\n', ' / ')[:110])

# 6g. Publication-fee proof upload → payment verification alert
import io as _io
CAPTURED.clear()
r = seller_client.post(f'/upload_payment/{ad_id}', data={
    'payment_proof': (_io.BytesIO(b'\xff\xd8\xff\xe0fake-jpeg-bytes'),
                      'proof_http_test.jpg'),
    'accept_terms': 'on',
}, content_type='multipart/form-data', follow_redirects=False)
check('POST /upload_payment/<id> accepted', r.status_code in (302, 200),
      f'status={r.status_code}')
check('payment-proof upload alerted the admin via WhatsApp',
      any('PREV PEMAN' in m for m in CAPTURED),
      (CAPTURED or [''])[0].replace('\n', ' / ')[:110])

# 6h. Legacy GKach purchase form → recharge approval alert
CAPTURED.clear()
r = anon.post('/achte_gkach', data={
    'whatsapp': SELLER_WA, 'amount': '1750',
      'document': (_io.BytesIO(b'\xff\xd8\xff' + b'legacy proof bytes'), 'legacy_gkach_test.jpg'),
}, content_type='multipart/form-data', follow_redirects=False)
check('POST /achte_gkach accepted', r.status_code == 302, f'status={r.status_code}')
check('legacy GKach request alerted the admin via WhatsApp',
      any('DEMANN RECHAJ GKACH' in m and '1750' in m for m in CAPTURED),
      (CAPTURED or [''])[0].replace('\n', ' / ')[:110])

CAPTURED.clear()
r = anon.post('/achte_gkach', data={
      'whatsapp': SELLER_WA, 'amount': '1750',
      'document': (_io.BytesIO(b'not an allowed proof'), 'malicious.php'),
}, content_type='multipart/form-data', follow_redirects=False)
check('legacy GKach proof rejects executable extensions',
        r.status_code == 302 and not CAPTURED, f'status={r.status_code}; alerts={len(CAPTURED)}')


print()
print('=' * 74)
print('7) ADMIN PANEL — /admin/alerts (queues + WhatsApp status + test)')
print('=' * 74)

# 7a. anonymous access must be refused
r = anon.get('/admin/alerts', follow_redirects=False)
check('anonymous GET /admin/alerts is blocked', r.status_code in (302, 401, 403),
      f'status={r.status_code}')

# 7b. pending queue summary
with app.app_context():
    s = AAA.pending_approvals_summary()
check('pending_approvals_summary has all queue keys',
      all(k in s for k in ('ads_under_review', 'ads_payment_pending',
                           'recharges_pending', 'withdrawals_pending',
                           'drivers_pending', 'organizations_pending',
                           'loans_pending', 'total')),
      sorted(s.keys()))
check('summary sees the pending ad + withdrawal + driver + org + loan',
      s['ads_under_review'] >= 1 and s['withdrawals_pending'] >= 1
      and s['drivers_pending'] >= 1 and s['organizations_pending'] >= 1
      and s['loans_pending'] >= 1 and s['recharges_pending'] >= 1
      and s['total'] >= 5, s)

# 7c. logged-in admin page
admin_client = app.test_client()
admin_client.post('/admin/login', data={'pseudo': 'AdminAlert',
                                        'password': 'admin-pass-1'},
                  follow_redirects=True)
r = admin_client.get('/admin/alerts')
check('GET /admin/alerts → 200 for admin', r.status_code == 200, f'status={r.status_code}')
body = r.get_data(as_text=True)
check('page shows the admin WhatsApp number', ADMIN_WA in body)
check('page shows the approval-alert heading', 'Alèt Apwobasyon' in body)
check('page shows the queue cards (piblisite an revizyon)',
      'Piblisite an revizyon' in body)
check('page shows the test-alert button', 'Voye yon alèt tès' in body)

# 7d. dashboard badge
r = admin_client.get('/admin/')
check('GET /admin/ dashboard → 200', r.status_code == 200, f'status={r.status_code}')
check('dashboard exposes the alerts quick link',
      '/admin/alerts' in r.get_data(as_text=True))

# 7e. one-click test alert
CAPTURED.clear()
r = admin_client.post('/admin/alerts/test', follow_redirects=False)
check('POST /admin/alerts/test redirects', r.status_code in (302, 200),
      f'status={r.status_code}')
check('test alert reached the WhatsApp channel',
      any('Tès alèt WhatsApp administratè' in m for m in CAPTURED),
      (CAPTURED or [''])[0].replace('\n', ' / ')[:110])
check('test alert also created an in-app admin notification',
      admin_notifications('admin_approval_generic') >= 1,
      admin_notifications('admin_approval_generic'))

# 7f. template render sanity (all admin_* templates used by the service exist)
with app.app_context():
    from app.services.notification_templates import get_template, render
    missing = [m['template'] for m in AAA.APPROVAL_KINDS.values()
               if get_template(m['template']) is None]
    check('every approval kind maps to an existing i18n template',
          not missing, missing)
    rendered = render('admin_withdrawal_request',
                      {'actor': 'X', 'amount': 10, 'description': 'test'}, lang='ht')
    check('i18n template renders the withdrawal message',
          'Demann retriz' in (rendered.get('title') or ''), rendered.get('title'))


print()
print('=' * 74)
passed = sum(1 for _, ok in results if ok)
failed = [n for n, ok in results if not ok]
print(f'RESULT: {passed}/{len(results)} checks passed')
if failed:
    print('FAILED CHECKS:')
    for n in failed:
        print('  -', n)
print('=' * 74)
sys.exit(1 if failed else 0)



