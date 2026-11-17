"""SELL flow: cart -> checkout -> negotiation -> escrow -> completion / cancellation.

Money invariants tested: GKach is conserved (buyer -T, seller +T), a buyer is
charged once, a seller is paid once, stock is never oversold, orders are atomic.
"""
import os
import sys
import uuid

import pytest

os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('SECRET_KEY', 'sell-tests-secret')
os.environ.setdefault('WTF_CSRF_ENABLED', 'False')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import create_app, db, limiter
from app.models.ad import Ad
from app.models.cart import CartItem
from app.models.delivery import Delivery
from app.models.delivery_item import DeliveryItem
from app.models.gkach_transaction import GkachTransaction
from app.models.user import User
from app.services.cart_service import CartService
from app.services.delivery_service import DeliveryService
from app.services.gkach_service import GkachService
from app.utils.validators import ValidationError

XHR = {'X-Requested-With': 'XMLHttpRequest'}


@pytest.fixture()
def app():
    a = create_app('testing')
    a.config['WTF_CSRF_ENABLED'] = False
    prev = limiter.enabled
    limiter.enabled = False
    yield a
    limiter.enabled = prev
    with a.app_context():
        db.session.remove()
        db.drop_all()


def _wa():
    return '+5094' + str(uuid.uuid4().int)[:7]


def _user(balance=0, admin=False):
    wa = _wa()
    u = User(whatsapp=wa, pseudo='s' + uuid.uuid4().hex[:10], name='T', auth_provider='whatsapp',
             is_active=True, is_admin=admin)
    u.set_password('Str0ng-Passw0rd!')
    db.session.add(u)
    db.session.commit()
    if balance:
        GkachService.add_balance(wa, balance)
    return u


def _ad(owner_wa, **over):
    kw = dict(ad_id=str(uuid.uuid4()), user_whatsapp=owner_wa, title='Telephone', description='ok',
              ad_type='sell', price_gkach=100, quantity=3, admin_status='approved',
              payment_status='approved')
    kw.update(over)
    ad = Ad(**kw)
    db.session.add(ad)
    db.session.commit()
    return ad.ad_id


class _AsUser:
    """Test client bound to one user.

    The ``world`` fixture keeps an app context open, and Flask-Login caches the
    current user in ``g`` for the life of that context. Without clearing it, every
    request after the first would silently run as the FIRST user.
    """
    def __init__(self, app, uid):
        self._c = app.test_client()
        with self._c.session_transaction() as s:
            s['_user_id'] = str(uid)
            s['_fresh'] = True

    def _fresh_identity(self):
        from flask import g
        g.pop('_login_user', None)

    def get(self, *a, **k):
        self._fresh_identity()
        return self._c.get(*a, **k)

    def post(self, *a, **k):
        self._fresh_identity()
        return self._c.post(*a, **k)


def _client(app, uid):
    return _AsUser(app, uid)


def bal(wa):
    return GkachService.get_balance(wa)


def total_money(*was):
    return sum(bal(w) for w in was)


@pytest.fixture()
def world(app):
    with app.app_context():
        seller, buyer, other = _user(0), _user(10_000), _user(5_000)
        ad = _ad(seller.whatsapp)
        yield {'app': app, 'seller': seller.whatsapp, 'sid': seller.id, 'buyer': buyer.whatsapp,
               'bid': buyer.id, 'other': other.whatsapp, 'oid': other.id, 'ad': ad}


def _snapshot(delivery_id):
    """What a CONCURRENT request would have read before another one committed.

    A detached copy of the row's values: it never refreshes, so any protection that
    relies on re-reading the status fails, and only a real compare-and-set UPDATE
    (``... WHERE status = <expected>``) can stop the second request.
    """
    import types
    row = Delivery.query.filter_by(delivery_id=delivery_id).one()
    return types.SimpleNamespace(**{c.name: getattr(row, c.name) for c in Delivery.__table__.columns})


def _negotiated(w, qty=2, cost=20):
    """A delivery that is awaiting buyer confirmation. Returns the delivery id."""
    CartService.add_to_cart(w['bid'], w['ad'], qty)
    items = CartService.get_user_cart(w['bid'])
    d = DeliveryService.create_delivery(
        w['buyer'], w['seller'], cart_items=[{'ad_id': i.product_id, 'quantity': i.quantity,
                                              'price_gkach': 100} for i in items],
        total_price=100 * qty, delivery_address='x')
    DeliveryService.set_delivery_cost(d.delivery_id, cost)
    return d.delivery_id


# ------------------------------ cart: validation ----------------------------
@pytest.mark.parametrize('qty', [0, -1, -999, 1001])
def test_cart_rejects_non_positive_or_absurd_quantities(world, qty):
    with pytest.raises(ValidationError):
        CartService.add_to_cart(world['bid'], world['ad'], qty)
    assert CartItem.query.filter_by(user_id=world['bid']).count() == 0


@pytest.mark.parametrize('qty', ['abc', '', '1.5', '1e3', 'NaN'])
def test_cart_route_returns_400_not_500_for_garbage_quantity(world, qty):
    c = _client(world['app'], world['bid'])
    r = c.post(f"/cart/add/{world['ad']}", data={'quantity': qty}, headers=XHR)
    assert r.status_code == 400, (qty, r.status_code)


def test_cart_negative_quantity_via_http_never_creates_a_negative_line(world):
    c = _client(world['app'], world['bid'])
    r = c.post(f"/cart/add/{world['ad']}", data={'quantity': '-5'}, headers=XHR)
    assert r.status_code == 400
    assert all(i.quantity > 0 for i in CartItem.query.all())


def test_cannot_buy_your_own_ad(world):
    with pytest.raises(ValidationError):
        CartService.add_to_cart(world['sid'], world['ad'], 1)


@pytest.mark.parametrize('over', [
    {'admin_status': 'under_review'}, {'admin_status': 'rejected'}, {'ad_type': 'publish'},
    {'quantity': 0}])
def test_cannot_buy_unavailable_listings(world, over):
    ad = _ad(world['seller'], **over)
    with pytest.raises(ValidationError):
        CartService.add_to_cart(world['bid'], ad, 1)
    with pytest.raises(ValidationError):
        CartService.add_to_cart(world['bid'], 'does-not-exist', 1)


def test_cart_cannot_exceed_stock_even_across_repeated_adds(world):
    CartService.add_to_cart(world['bid'], world['ad'], 2)          # stock is 3
    CartService.add_to_cart(world['bid'], world['ad'], 1)
    with pytest.raises(ValidationError):
        CartService.add_to_cart(world['bid'], world['ad'], 1)       # would be 4
    assert CartItem.query.filter_by(user_id=world['bid']).one().quantity == 3


def test_update_quantity_is_bounded_and_limited_to_open_cart_lines(world):
    CartService.add_to_cart(world['bid'], world['ad'], 1)
    item = CartItem.query.filter_by(user_id=world['bid']).one()
    with pytest.raises(ValidationError):
        CartService.update_quantity(world['bid'], item.id, 99)
    item.negotiation_status = 'buyer_submitted'                     # already in negotiation
    db.session.commit()
    with pytest.raises(ValidationError):
        CartService.update_quantity(world['bid'], item.id, 2)
    assert db.session.get(CartItem, item.id).quantity == 1


def test_legacy_ads_without_stock_figure_stay_purchasable(world):
    ad = _ad(world['seller'])
    Ad.query.filter_by(ad_id=ad).update({'quantity': None})        # real legacy row: NULL stock
    db.session.commit()
    CartService.add_to_cart(world['bid'], ad, 5)
    assert CartItem.query.filter_by(user_id=world['bid'], product_id=ad).one().quantity == 5


# -------------------------------- checkout ----------------------------------
def test_regular_form_checkout_really_creates_the_order(world):
    CartService.add_to_cart(world['bid'], world['ad'], 2)
    c = _client(world['app'], world['bid'])
    r = c.post('/cart/checkout')                                    # plain form post, no XHR header
    assert r.status_code == 302
    assert Delivery.query.filter_by(buyer_whatsapp=world['buyer']).count() == 1
    assert CartItem.query.filter_by(user_id=world['bid']).count() == 0     # cart emptied


def test_ajax_checkout_creates_one_order_per_seller(world):
    ad2 = _ad(_user(0).whatsapp)
    CartService.add_to_cart(world['bid'], world['ad'], 1)
    CartService.add_to_cart(world['bid'], ad2, 1)
    r = _client(world['app'], world['bid']).post('/cart/checkout', headers=XHR)
    assert r.status_code == 200 and r.json['success']
    assert Delivery.query.filter_by(buyer_whatsapp=world['buyer']).count() == 2


def test_checkout_revalidates_listings_at_purchase_time(world):
    CartService.add_to_cart(world['bid'], world['ad'], 1)
    Ad.query.filter_by(ad_id=world['ad']).update({'admin_status': 'rejected'})
    db.session.commit()
    r = _client(world['app'], world['bid']).post('/cart/checkout', headers=XHR)
    assert r.status_code == 400
    assert Delivery.query.count() == 0 and CartItem.query.filter_by(user_id=world['bid']).count() == 1


def test_checkout_refuses_a_cart_that_now_exceeds_stock(world):
    CartService.add_to_cart(world['bid'], world['ad'], 3)
    Ad.query.filter_by(ad_id=world['ad']).update({'quantity': 1})   # someone else bought 2
    db.session.commit()
    r = _client(world['app'], world['bid']).post('/cart/checkout', headers=XHR)
    assert r.status_code == 400 and Delivery.query.count() == 0


def test_multi_seller_checkout_is_all_or_nothing(world, monkeypatch):
    ad2 = _ad(_user(0).whatsapp)
    CartService.add_to_cart(world['bid'], world['ad'], 1)
    CartService.add_to_cart(world['bid'], ad2, 1)
    real, calls = DeliveryService.create_delivery, {'n': 0}

    def flaky(*a, **k):
        calls['n'] += 1
        if calls['n'] == 2:
            raise RuntimeError('db hiccup on the 2nd seller')
        return real(*a, **k)
    monkeypatch.setattr(DeliveryService, 'create_delivery', staticmethod(flaky))
    r = _client(world['app'], world['bid']).post('/cart/checkout', headers=XHR)
    assert r.status_code == 500
    assert Delivery.query.count() == 0                              # no half-created orders
    assert CartItem.query.filter_by(user_id=world['bid']).count() == 2   # cart intact -> safe retry
    monkeypatch.undo()
    assert _client(world['app'], world['bid']).post('/cart/checkout', headers=XHR).status_code == 200
    assert Delivery.query.count() == 2                              # the retry creates each order ONCE


def test_double_checkout_cannot_duplicate_orders_even_with_a_stale_cart(world, monkeypatch):
    CartService.add_to_cart(world['bid'], world['ad'], 1)
    stale = CartService.get_user_cart(world['bid'])
    c = _client(world['app'], world['bid'])
    assert c.post('/cart/checkout', headers=XHR).status_code == 200
    monkeypatch.setattr(CartService, 'get_user_cart', staticmethod(lambda uid: stale))   # 2nd request raced
    r = c.post('/cart/checkout', headers=XHR)
    assert r.status_code in (400, 409)
    assert Delivery.query.filter_by(buyer_whatsapp=world['buyer']).count() == 1


def test_order_price_comes_from_the_listing_not_the_client(world):
    CartService.add_to_cart(world['bid'], world['ad'], 2)
    c = _client(world['app'], world['bid'])
    c.post('/cart/checkout', data={'price_gkach': '1', 'total': '1', 'total_price': '1'}, headers=XHR)
    d = Delivery.query.one()
    assert d.total_price == 200 and DeliveryItem.query.one().price_gkach == 100


def test_create_delivery_rejects_self_dealing_and_bad_totals(world):
    with pytest.raises(ValidationError):
        DeliveryService.create_delivery(world['seller'], world['seller'], total_price=100)
    with pytest.raises(ValidationError):
        DeliveryService.create_delivery(world['buyer'], world['seller'], total_price=-100)
    with pytest.raises(ValidationError):
        DeliveryService.create_delivery(world['buyer'], world['seller'], total_price=100,
                                        cart_items=[{'ad_id': world['ad'], 'quantity': 0, 'price_gkach': 100}])
    assert Delivery.query.count() == 0


# ----------------------------- escrow: confirm/complete ----------------------
def test_buyer_cannot_confirm_before_the_shipping_cost_is_negotiated(world):
    CartService.add_to_cart(world['bid'], world['ad'], 1)
    d = DeliveryService.create_delivery(world['buyer'], world['seller'], total_price=100,
                                        cart_items=[{'ad_id': world['ad'], 'quantity': 1, 'price_gkach': 100}])
    before = bal(world['buyer'])
    with pytest.raises(ValidationError):
        DeliveryService.confirm_delivery(d.delivery_id, world['buyer'])        # still 'negotiating'
    assert bal(world['buyer']) == before and db.session.get(Delivery, d.delivery_id).status == 'negotiating'
    r = _client(world['app'], world['bid']).post(f'/delivery/confirm/{d.delivery_id}')
    assert r.status_code == 302 and bal(world['buyer']) == before


def test_happy_path_conserves_gkach_and_decrements_stock(world):
    start = total_money(world['buyer'], world['seller'])
    did = _negotiated(world, qty=2, cost=20)                                   # 2*100 + 20 = 220
    assert bal(world['buyer']) == 10_000 and bal(world['seller']) == 0         # nothing moved yet
    DeliveryService.confirm_delivery(did, world['buyer'], expected_total=220)
    assert bal(world['buyer']) == 10_000 - 220 and bal(world['seller']) == 0   # held, not yet paid
    assert Ad.query.filter_by(ad_id=world['ad']).one().quantity == 1
    DeliveryService.mark_completed(did)
    assert bal(world['seller']) == 220 and bal(world['buyer']) == 10_000 - 220
    assert total_money(world['buyer'], world['seller']) == start                # conservation
    types = sorted(t.transaction_type for t in GkachTransaction.query.filter(
        GkachTransaction.user_whatsapp.in_([world['buyer'], world['seller']])) if t.amount == 220)
    assert types == ['purchase_hold', 'sale']


def test_changed_price_between_view_and_confirm_is_refused(world):
    did = _negotiated(world, qty=1, cost=20)                                   # buyer saw 120
    DeliveryService.set_delivery_cost(did, 900)                                # seller bumps it
    before = bal(world['buyer'])
    with pytest.raises(ValidationError):
        DeliveryService.confirm_delivery(did, world['buyer'], expected_total=120)
    assert bal(world['buyer']) == before


def test_confirm_form_sends_the_total_the_buyer_saw(world):
    did = _negotiated(world, qty=1, cost=20)
    c = _client(world['app'], world['bid'])
    page = c.get(f'/delivery/view/{did}').data.decode()
    assert 'name="expected_total" value="120"' in page
    DeliveryService.set_delivery_cost(did, 900)
    r = c.post(f'/delivery/confirm/{did}', data={'expected_total': '120'})
    assert bal(world['buyer']) == 10_000                                       # refused, nothing charged


def test_only_the_buyer_can_confirm_and_complete(world):
    did = _negotiated(world)
    for who in ('seller', 'other'):
        with pytest.raises(ValidationError):
            DeliveryService.confirm_delivery(did, world[who])
    DeliveryService.confirm_delivery(did, world['buyer'])
    for uid in (world['sid'], world['oid']):
        _client(world['app'], uid).post(f'/delivery/complete/{did}')
    assert db.session.get(Delivery, did).status == 'awaiting_delivery' and bal(world['seller']) == 0
    _client(world['app'], world['bid']).post(f'/delivery/complete/{did}')           # the real buyer can
    assert db.session.get(Delivery, did).status == 'completed' and bal(world['seller']) == 220


def test_confirming_twice_charges_once_even_with_a_stale_copy(world, monkeypatch):
    did = _negotiated(world, qty=1, cost=0)
    stale = _snapshot(did)
    assert stale.status == 'awaiting_buyer_confirmation'
    DeliveryService.confirm_delivery(did, world['buyer'])
    assert bal(world['buyer']) == 9_900
    monkeypatch.setattr(DeliveryService, 'get_delivery', staticmethod(lambda _id: stale))   # racing request
    with pytest.raises(ValidationError):
        DeliveryService.confirm_delivery(did, world['buyer'])
    assert bal(world['buyer']) == 9_900                                        # not charged twice


def test_completing_twice_pays_the_seller_once_even_with_a_stale_copy(world, monkeypatch):
    did = _negotiated(world, qty=1, cost=0)
    DeliveryService.confirm_delivery(did, world['buyer'])
    stale = _snapshot(did)
    assert stale.status == 'awaiting_delivery'
    DeliveryService.mark_completed(did)
    assert bal(world['seller']) == 100
    monkeypatch.setattr(DeliveryService, 'get_delivery', staticmethod(lambda _id: stale))   # racing request
    with pytest.raises(ValidationError):
        DeliveryService.mark_completed(did)
    assert bal(world['seller']) == 100                                         # money not minted


def test_complete_requires_a_confirmed_order(world):
    did = _negotiated(world)
    with pytest.raises(ValidationError):
        DeliveryService.mark_completed(did)                                    # never paid for
    assert bal(world['seller']) == 0


def test_insufficient_funds_leaves_no_trace(world):
    poor = _user(10)
    ad = _ad(world['seller'])
    CartService.add_to_cart(poor.id, ad, 1)
    d = DeliveryService.create_delivery(poor.whatsapp, world['seller'], total_price=100,
                                        cart_items=[{'ad_id': ad, 'quantity': 1, 'price_gkach': 100}])
    DeliveryService.set_delivery_cost(d.delivery_id, 0)
    with pytest.raises(Exception):
        DeliveryService.confirm_delivery(d.delivery_id, poor.whatsapp)
    db.session.rollback()
    assert bal(poor.whatsapp) == 10
    assert db.session.get(Delivery, d.delivery_id).status == 'awaiting_buyer_confirmation'
    assert Ad.query.filter_by(ad_id=ad).one().quantity == 3                    # stock untouched


def test_the_last_item_cannot_be_sold_twice(world):
    ad = _ad(world['seller'], quantity=1)
    out = []
    for who in (world['bid'], world['oid']):
        u = db.session.get(User, who)
        d = DeliveryService.create_delivery(u.whatsapp, world['seller'], total_price=100,
                                            cart_items=[{'ad_id': ad, 'quantity': 1, 'price_gkach': 100}])
        DeliveryService.set_delivery_cost(d.delivery_id, 0)
        out.append((u.whatsapp, d.delivery_id))
    DeliveryService.confirm_delivery(out[0][1], out[0][0])
    before = bal(out[1][0])
    with pytest.raises(ValidationError):
        DeliveryService.confirm_delivery(out[1][1], out[1][0])                 # stock is gone
    assert bal(out[1][0]) == before                                            # second buyer not charged
    assert Ad.query.filter_by(ad_id=ad).one().quantity == 0


# -------------------------------- cancellation -------------------------------
def test_cancel_before_payment_moves_no_money(world):
    did = _negotiated(world)
    DeliveryService.cancel_delivery(did, world['buyer'])
    assert db.session.get(Delivery, did).status == 'cancelled' and bal(world['buyer']) == 10_000
    assert Ad.query.filter_by(ad_id=world['ad']).one().quantity == 3
    with pytest.raises(ValidationError):
        DeliveryService.confirm_delivery(did, world['buyer'])                  # cancelled is final


def test_seller_cancel_after_payment_refunds_the_buyer_and_restocks(world):
    start = total_money(world['buyer'], world['seller'])
    did = _negotiated(world, qty=2, cost=20)
    DeliveryService.confirm_delivery(did, world['buyer'])
    assert Ad.query.filter_by(ad_id=world['ad']).one().quantity == 1
    DeliveryService.cancel_delivery(did, world['seller'])
    assert bal(world['buyer']) == 10_000 and bal(world['seller']) == 0
    assert total_money(world['buyer'], world['seller']) == start
    assert Ad.query.filter_by(ad_id=world['ad']).one().quantity == 3           # stock restored
    assert db.session.get(Delivery, did).status == 'cancelled'
    assert GkachTransaction.query.filter_by(user_whatsapp=world['buyer'], transaction_type='refund').count() == 1


def test_cancel_cannot_refund_twice(world, monkeypatch):
    did = _negotiated(world, qty=1, cost=0)
    DeliveryService.confirm_delivery(did, world['buyer'])
    stale = _snapshot(did)
    assert stale.status == 'awaiting_delivery'
    DeliveryService.cancel_delivery(did, world['seller'])
    monkeypatch.setattr(DeliveryService, 'get_delivery', staticmethod(lambda _id: stale))
    with pytest.raises(ValidationError):
        DeliveryService.cancel_delivery(did, world['seller'])
    assert bal(world['buyer']) == 10_000                                       # refunded exactly once


def test_who_may_cancel(world):
    did = _negotiated(world)
    with pytest.raises(ValidationError):
        DeliveryService.cancel_delivery(did, world['other'])                   # stranger
    DeliveryService.confirm_delivery(did, world['buyer'])
    with pytest.raises(ValidationError):
        DeliveryService.cancel_delivery(did, world['buyer'])                   # buyer cannot claw back paid order
    with pytest.raises(ValidationError):
        DeliveryService.cancel_delivery(did, world['other'])
    DeliveryService.cancel_delivery(did, world['other'], is_admin=True)        # admin may (refund)
    assert bal(world['buyer']) == 10_000


def test_completed_orders_cannot_be_cancelled(world):
    did = _negotiated(world, qty=1, cost=0)
    DeliveryService.confirm_delivery(did, world['buyer'])
    DeliveryService.mark_completed(did)
    for who, adm in (('seller', False), ('other', True)):
        with pytest.raises(ValidationError):
            DeliveryService.cancel_delivery(did, world[who], is_admin=adm)
    assert bal(world['seller']) == 100 and bal(world['buyer']) == 9_900


def test_cancel_route_enforces_authorization(world):
    did = _negotiated(world)
    DeliveryService.confirm_delivery(did, world['buyer'])
    _client(world['app'], world['oid']).post(f'/delivery/cancel/{did}')
    _client(world['app'], world['bid']).post(f'/delivery/cancel/{did}')
    assert db.session.get(Delivery, did).status == 'awaiting_delivery'
    r = _client(world['app'], world['sid']).post(f'/delivery/cancel/{did}')
    assert r.status_code == 302 and db.session.get(Delivery, did).status == 'cancelled'
    assert bal(world['buyer']) == 10_000


def test_a_negative_add_cannot_shrink_an_existing_cart_line(world):
    CartService.add_to_cart(world['bid'], world['ad'], 2)
    with pytest.raises(ValidationError):
        CartService.add_to_cart(world['bid'], world['ad'], -1)       # 2 + (-1) = 1 would pass a stock check
    assert CartItem.query.filter_by(user_id=world['bid']).one().quantity == 2
    r = _client(world['app'], world['bid']).post(f"/cart/add/{world['ad']}", data={'quantity': '-1'}, headers=XHR)
    assert r.status_code == 400 and CartItem.query.filter_by(user_id=world['bid']).one().quantity == 2


def test_concurrent_checkout_with_plain_loaded_values_is_stopped_by_the_row_count(world, monkeypatch):
    """The second request already LOADED the cart before the first one committed, so
    it holds ordinary, non-expired values. Only the delete-by-id row count can stop it."""
    import types
    CartService.add_to_cart(world['bid'], world['ad'], 1)
    ad_obj = Ad.query.filter_by(ad_id=world['ad']).one()
    loaded = [types.SimpleNamespace(id=i.id, product_id=i.product_id, quantity=i.quantity,
                                    shipping_fee=0.0, ad=ad_obj)
              for i in CartService.get_user_cart(world['bid'])]
    c = _client(world['app'], world['bid'])
    assert c.post('/cart/checkout', headers=XHR).status_code == 200
    assert Delivery.query.filter_by(buyer_whatsapp=world['buyer']).count() == 1
    monkeypatch.setattr(CartService, 'get_user_cart', staticmethod(lambda uid: loaded))
    r = c.post('/cart/checkout', headers=XHR)
    assert r.status_code == 409
    assert Delivery.query.filter_by(buyer_whatsapp=world['buyer']).count() == 1     # no duplicate order
