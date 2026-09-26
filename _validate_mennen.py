"""End-to-end validation for the new Mennen M driver workflow (P0 + real driver registry)."""
import os
import sys

os.environ['FLASK_ENV'] = 'testing'
os.environ['RATELIMIT_ENABLED'] = '0'
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models.user import User
from app.models.mennem_driver import MennemDriver
from app.models.mennem_trip import MennemTrip

app = create_app('testing')

results = []


def check(name, ok, extra=''):
    results.append((name, ok))
    print(('PASS' if ok else 'FAIL'), '-', name, ('| ' + str(extra)) if extra else '')


with app.app_context():
    db.create_all()

    admin = User(name='Admin Test', pseudo='AdminTest', whatsapp='+50942882076',
                 is_admin=True, is_active=True)
    admin.set_password('admin-pass-1')
    db.session.add(admin)
    pax = User(name='Pasaje Test', pseudo='Pasaje', whatsapp='+50955550001', is_active=True)
    pax.set_password('pax-pass-1')
    db.session.add(pax)
    db.session.commit()

anon = app.test_client()
admin_c = app.test_client()
pax_c = app.test_client()

# 1. index
r = anon.get('/mennenm/')
check('GET /mennenm/', r.status_code == 200, f'status={r.status_code}')

# 2. register_driver GET
r = anon.get('/mennenm/register_driver')
check('GET register_driver', r.status_code == 200, f'status={r.status_code}')

# 3. register_driver POST valid
r = anon.post('/mennenm/register_driver', data={
    'name': 'Jean Pierre',
    'phone': '+50933330001',
    'address': 'Delmas 33',
    'price': '150',
}, follow_redirects=False)
with app.app_context():
    d = MennemDriver.query.filter_by(whatsapp='+50933330001').first()
check('POST register_driver creates row', r.status_code == 302 and d is not None,
      f'status={r.status_code} driver={d is not None}')
check('driver starts unverified+inactive', d is not None and not d.is_verified and not d.is_active)
check('driver city guessed', d is not None and d.city == 'Delmas', f'city={d.city if d else None}')
driver_id = d.id if d else 0

# 4. duplicate whatsapp rejected
r = anon.post('/mennenm/register_driver', data={
    'name': 'Autre Chofe', 'phone': '+50933330001', 'address': 'Carrefour', 'price': '200',
}, follow_redirects=False)
with app.app_context():
    count = MennemDriver.query.filter_by(whatsapp='+50933330001').count()
check('duplicate whatsapp not duplicated', count == 1, f'count={count}')

# 5. invalid whatsapp rejected
r = anon.post('/mennenm/register_driver', data={
    'name': 'Mauvais Numero', 'phone': '123', 'address': 'Delmas', 'price': '150',
})
with app.app_context():
    bad = MennemDriver.query.filter_by(name='Mauvais Numero').first()
check('invalid whatsapp rejected', bad is None)

# 6. find (anonymous) hides unverified driver
r = anon.post('/mennenm/find', data={'from': 'Delmas', 'to': 'Pétion-Ville'})
check('find hides unverified driver', ('Jean Pierre' not in r.get_data(as_text=True)),
      f'status={r.status_code}')

# 7. admin requires login
r = anon.get('/mennenm/admin')
check('admin redirects anonymous', r.status_code == 302, f'status={r.status_code}')

# 8. login as admin + view admin page
r = admin_c.post('/auth/login', data={'identifier': 'AdminTest', 'password': 'admin-pass-1'})
check('admin login', r.status_code in (302, 200), f'status={r.status_code}')
r = admin_c.get('/mennenm/admin')
check('GET /mennenm/admin as admin', r.status_code == 200, f'status={r.status_code}')
check('admin page lists pending driver', 'Jean Pierre' in r.get_data(as_text=True))

# 9. approve
r = admin_c.post(f'/mennenm/admin/driver/{driver_id}/toggle', data={'action': 'activate'})
with app.app_context():
    d = db.session.get(MennemDriver, driver_id)
check('admin approve toggles verified+active', r.status_code == 302 and d.is_verified and d.is_active)

# 10. find shows driver now
r = anon.post('/mennenm/find', data={'from': 'Delmas', 'to': 'Pétion-Ville'})
html = r.get_data(as_text=True)
check('find shows approved driver', 'Jean Pierre' in html, f'status={r.status_code}')
check('find shows suggested market price (P-a-P intra ~150)',
      'Pri mache sijere: ~150 Gk' in html)

# 11. book GET as anonymous
r = anon.get(f'/mennenm/book/{driver_id}/Delmas/Petion-Ville')
html = r.get_data(as_text=True)
check('GET book shows driver+fee', r.status_code == 200 and '150' in html, f'status={r.status_code}')
check('book shows suggested price + negotiation hint',
      'Pri mache sijere pou wout sa a: ~150 Gk' in html and 'negosye pri a' in html)

# 12. book with bad id -> no 500
r = anon.get('/mennenm/book/99999/Delmas/Petion-Ville')
check('book with bad id redirects (no 500)', r.status_code == 302, f'status={r.status_code}')

# 13. login as passenger, start a NEGOTIATION (no Gkach debited yet)
r = pax_c.post('/auth/login', data={'identifier': 'Pasaje', 'password': 'pax-pass-1'})
check('passenger login', r.status_code in (302, 200), f'status={r.status_code}')
r = pax_c.post(f'/mennenm/book/{driver_id}/Delmas/Petion-Ville', data={})
loc = r.headers.get('Location', '')
check('POST book redirects to negotiation page', r.status_code == 302 and '/mennenm/trip/' in loc,
      f'status={r.status_code} loc={loc}')
with app.app_context():
    _pax = User.query.filter_by(whatsapp='+50955550001').first()
    trip = MennemTrip.query.filter_by(passenger_id=_pax.id).first()
    d = db.session.get(MennemDriver, driver_id)
check('trip created with negotiating status + client proposal',
      trip is not None and trip.status == 'negotiating' and trip.proposed_price == 150,
      f"status={trip.status if trip else None} proposed={trip.proposed_price if trip else None}")
check('no Gkach debited yet / trips_count still 0',
      d is not None and d.trips_count == 0, f'trips={d.trips_count if d else None}')

# 14. trip page (client view) shows negotiation UI
r = pax_c.get(f'/mennenm/trip/{trip.id}')
html = r.get_data(as_text=True)
check('GET trip page as client', r.status_code == 200 and 'Negosyasyon' in html,
      f'status={r.status_code}')
check('trip page shows suggested market price', 'Pri mache sijere pou wout sa a' in html)
check('trip page has WhatsApp notify link for the other party',
      'wa.me/' in html and 'Notifye' in html)

# 15. another user cannot access the trip (403)
r = anon.get(f'/mennenm/trip/{trip.id}')
check('trip page blocked for strangers', r.status_code in (302, 403), f'status={r.status_code}')

# 16. client proposes a lower price
r = pax_c.post(f'/mennenm/trip/{trip.id}/propose', data={'price': '100'})
with app.app_context():
    trip = db.session.get(MennemTrip, trip.id)
check('client proposes 100 Gk', r.status_code == 302 and trip.proposed_price == 100,
      f'proposed={trip.proposed_price}')

# 17. driver user + counter-offer
with app.app_context():
    drv_user = User(name='Jean Chofe', pseudo='JeanChofe', whatsapp='+50933330001', is_active=True)
    drv_user.set_password('drv-pass-1')
    db.session.add(drv_user)
    db.session.commit()
drv_c = app.test_client()
r = drv_c.post('/auth/login', data={'identifier': 'JeanChofe', 'password': 'drv-pass-1'})
check('driver login (linked by whatsapp)', r.status_code in (302, 200), f'status={r.status_code}')
r = drv_c.get(f'/mennenm/trip/{trip.id}')
check('driver sees trip page', r.status_code == 200, f'status={r.status_code}')
r = drv_c.post(f'/mennenm/trip/{trip.id}/counter', data={'price': '120'})
with app.app_context():
    trip = db.session.get(MennemTrip, trip.id)
check('driver counters 120 Gk', r.status_code == 302 and trip.counter_price == 120,
      f'counter={trip.counter_price}')

# 18. client accepts driver's counter -> accepted
r = pax_c.post(f'/mennenm/trip/{trip.id}/accept')
with app.app_context():
    trip = db.session.get(MennemTrip, trip.id)
check('client accepts counter -> accepted',
      r.status_code == 302 and trip.status == 'accepted' and trip.accepted_price == 120,
      f"status={trip.status} accepted={trip.accepted_price}")

# 19. client pays in DEMO mode -> status demo, no debit, trips_count +1
r = pax_c.post(f'/mennenm/trip/{trip.id}/pay')
with app.app_context():
    trip = db.session.get(MennemTrip, trip.id)
    d = db.session.get(MennemDriver, driver_id)
check('client pays (demo) -> status demo', r.status_code == 302 and trip.status == 'demo',
      f'status={trip.status}')
check('driver trips_count incremented after pay', d is not None and d.trips_count == 1,
      f'trips={d.trips_count if d else None}')
check('negotiation history has events', len(trip.history()) >= 4, f'events={len(trip.history())}')

# 20. success page + my-trips page
r = pax_c.get(f'/mennenm/success/{trip.id}')
check('GET success page', r.status_code == 200, f'status={r.status_code}')
r = pax_c.get('/mennenm/my-trips')
check('GET my-trips (client)', r.status_code == 200 and 'Delmas' in r.get_data(as_text=True),
      f'status={r.status_code}')
r = drv_c.get('/mennenm/my-trips')
check('GET my-trips (driver)', r.status_code == 200, f'status={r.status_code}')

# 21. client completes the trip
r = pax_c.post(f'/mennenm/trip/{trip.id}/complete')
with app.app_context():
    trip = db.session.get(MennemTrip, trip.id)
check('client completes trip', r.status_code == 302 and trip.status == 'completed',
      f'status={trip.status}')

# 22. cannot pay again after completed
r = pax_c.post(f'/mennenm/trip/{trip.id}/pay')
with app.app_context():
    trip = db.session.get(MennemTrip, trip.id)
check('pay after completed rejected (stays completed)',
      r.status_code == 302 and trip.status == 'completed', f'status={trip.status}')

# ------------------------------------------------------------------
# 23. REAL-MODE Gkach flow (demo mode monkeypatched off)
# ------------------------------------------------------------------
import mennem.app as _mennem_mod
from app.services.gkach_service import GkachService

_mennem_mod.MENNEM_DEMO_MODE = False
try:
    # 23a. client rates trip 1 (demo-completed) 5 stars -> driver rating set
    r = pax_c.post(f'/mennenm/trip/{trip.id}/rate', data={'rating': '5'})
    with app.app_context():
        d = db.session.get(MennemDriver, driver_id)
    check('client rates completed trip 5/5 -> driver rating updated',
          r.status_code == 302 and d.rating == 5.0, f'rating={d.rating if d else None}')
    r = pax_c.post(f'/mennenm/trip/{trip.id}/rate', data={'rating': '1'})
    check('double rating rejected', r.status_code == 302)

    # fund the passenger for real payments
    with app.app_context():
        GkachService.add_balance('+50955550001', 1000, 'test funding')
        pax_bal0 = GkachService.get_balance('+50955550001')

    # 23b. real-mode trip: negotiate -> pay (debit) -> complete (credit driver)
    r = pax_c.post(f'/mennenm/book/{driver_id}/Delmas/Petion-Ville', data={})
    with app.app_context():
        trip2 = MennemTrip.query.filter_by(passenger_id=_pax.id).order_by(
            MennemTrip.id.desc()).first()
    # client proposes 100, driver accepts it
    r = pax_c.post(f'/mennenm/trip/{trip2.id}/propose', data={'price': '100'})
    r = drv_c.post(f'/mennenm/trip/{trip2.id}/accept')
    with app.app_context():
        trip2 = db.session.get(MennemTrip, trip2.id)
    check('real trip accepted at 100 Gk',
          trip2.status == 'accepted' and trip2.accepted_price == 100,
          f"status={trip2.status} accepted={trip2.accepted_price}")

    r = pax_c.post(f'/mennenm/trip/{trip2.id}/pay')
    with app.app_context():
        bal_after_pay = GkachService.get_balance('+50955550001')
    check('real pay debits client 100 Gk',
          r.status_code == 302 and pax_bal0 - bal_after_pay == 100,
          f'before={pax_bal0} after={bal_after_pay}')
    with app.app_context():
        drv_bal0 = GkachService.get_balance('+50933330001')
    check('driver NOT credited before completion', drv_bal0 == 0, f'balance={drv_bal0}')

    r = pax_c.post(f'/mennenm/trip/{trip2.id}/complete')
    with app.app_context():
        drv_bal1 = GkachService.get_balance('+50933330001')
    with app.app_context():
        trip2 = db.session.get(MennemTrip, trip2.id)
        d = db.session.get(MennemDriver, driver_id)
    # 2% platform commission (same as MACHE): 100 - 2 = 98 to the driver
    check('completion credits driver 98 Gk (2% commission)',
          drv_bal1 == 98, f'balance={drv_bal1}')
    check('real trip completed', trip2.status == 'completed', f'status={trip2.status}')

    # 23c. client rates trip 2 at 4 -> weighted avg (5.0*1 + 4) / 2 = 4.5
    r = pax_c.post(f'/mennenm/trip/{trip2.id}/rate', data={'rating': '4'})
    with app.app_context():
        d = db.session.get(MennemDriver, driver_id)
    check('second rating -> weighted avg 4.5', r.status_code == 302 and d.rating == 4.5,
          f'rating={d.rating}')

    # 23d. cancel after real pay -> refund
    r = pax_c.post(f'/mennenm/book/{driver_id}/Delmas/Petion-Ville', data={})
    with app.app_context():
        trip3 = MennemTrip.query.filter_by(passenger_id=_pax.id).order_by(
            MennemTrip.id.desc()).first()
    pax_c.post(f'/mennenm/trip/{trip3.id}/propose', data={'price': '80'})
    drv_c.post(f'/mennenm/trip/{trip3.id}/accept')
    pax_c.post(f'/mennenm/trip/{trip3.id}/pay')
    with app.app_context():
        bal_before_cancel = GkachService.get_balance('+50955550001')
    r = pax_c.post(f'/mennenm/trip/{trip3.id}/cancel')
    with app.app_context():
        bal_after_cancel = GkachService.get_balance('+50955550001')
    with app.app_context():
        trip3 = db.session.get(MennemTrip, trip3.id)
    check('cancel after real pay refunds client 80 Gk',
          r.status_code == 302 and trip3.status == 'cancelled'
          and bal_after_cancel - bal_before_cancel == 80,
          f"status={trip3.status} refund={bal_after_cancel - bal_before_cancel}")

    # 23e. rate blocked on non-completed trip
    r = pax_c.post(f'/mennenm/trip/{trip3.id}/rate', data={'rating': '5'})
    check('rating blocked on cancelled trip', r.status_code == 302)
finally:
    _mennem_mod.MENNEM_DEMO_MODE = True

# ------------------------------------------------------------------
# 24. P3 — badge "action pending" + 24h negotiation expiry
# ------------------------------------------------------------------
from datetime import datetime as _dt, timedelta as _td

# 24a. badge: driver has 1 pending (fresh negotiating trip 3? it's cancelled;
# make a new one) -> book + propose, badge on index page should show 1
r = pax_c.post(f'/mennenm/book/{driver_id}/Delmas/Petion-Ville', data={})
with app.app_context():
    trip4 = MennemTrip.query.filter_by(passenger_id=_pax.id).order_by(
        MennemTrip.id.desc()).first()
r = drv_c.get('/mennenm/')
import re as _re
m = _re.search(r'Mes Vwayaj\s*<span[^>]*>(\d+)</span>', r.get_data(as_text=True)) or \
    _re.search(r'Mes Vwayaj[\s\S]{0,200}?>(\d+)</span>', r.get_data(as_text=True))
check('driver badge shows 1 pending action on index',
      r.status_code == 200 and m is not None and m.group(1) == '1',
      f"badge={m.group(1) if m else None}")
r = pax_c.get('/mennenm/')
check('client badge empty before counter (0 shown or absent)',
      r.status_code == 200 and 'dc2626' not in r.get_data(as_text=True))

# 24b. expiry: backdate trip4 beyond 24h -> index visit cancels it
with app.app_context():
    t4 = db.session.get(MennemTrip, trip4.id)
    t4.created_at = _dt.utcnow() - _td(hours=25)
    db.session.commit()
r = pax_c.get('/mennenm/')
with app.app_context():
    t4 = db.session.get(MennemTrip, trip4.id)
check('stale negotiation (>24h) auto-cancelled on index visit',
      r.status_code == 200 and t4.status == 'cancelled', f'status={t4.status}')
expired_ev = any('ekspire' in (ev.get('message') or '') for ev in t4.history())
check('expiry event recorded in history', expired_ev)

print()
fails = [n for n, ok in results if not ok]
print(f'=== {len(results) - len(fails)}/{len(results)} passed ===')
if fails:
    print('FAILED:', fails)
    sys.exit(1)
print('ALL OK')