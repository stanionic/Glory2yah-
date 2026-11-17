"""HTML pages of the Wi-Fi zone (the 'Sèvis' menu entry points here).

Read-only dashboard + two actions (become a vendor, renew) that go through the same,
already-tested services as the JSON API. Nothing secret is ever rendered (no tickets,
voucher codes/hashes, keys or tokens).
"""
import math
import uuid
from datetime import timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.services.gkach_service import GkachService
from app.wifi import gateway_service as gs
from app.wifi import subscription_service as ss
from app.wifi import vendor_service as vs
from app.wifi.models import (GATEWAY_ENROLLED, WifiGateway, WifiPackage, WifiPurchase, WifiVendor,
                             WifiVoucher)
from app.wifi.policy import get_policy

wifi_ui_bp = Blueprint('wifi_ui', __name__, url_prefix='/wifi')

ONLINE_WINDOW = timedelta(minutes=5)       # ~10 missed 30-second heartbeats
_STATE_LABEL = {'TRIAL': 'ESSAI', 'SUBSCRIBED': 'ABONNÉ', 'GRACE': 'GRÂCE', 'EXPIRED': 'EXPIRÉ',
                'NO_PLAN': 'SANS PLAN', 'SUSPENDED': 'SUSPENDU'}


def ago(dt, now=None):
    """Short Kreyòl 'time since' text; None -> 'jamè'."""
    if dt is None:
        return 'jamè'
    secs = max(0, int(((now or vs.utcnow()) - dt).total_seconds()))
    if secs < 60:
        return 'kounye a'
    if secs < 3600:
        return f'{secs // 60} minit'
    if secs < 86400:
        return f'{secs // 3600} èdtan'
    return f'{secs // 86400} jou'


def gateway_status(gw, now=None):
    if gw.status != GATEWAY_ENROLLED:
        return gw.status                                   # SUSPENDED / REVOKED
    seen = gw.last_seen_at
    return 'ONLINE' if seen and ((now or vs.utcnow()) - seen) <= ONLINE_WINDOW else 'OFFLINE'


def _vendor_context(user, vendor):
    now = vs.utcnow()
    access = ss.access_state(vendor)
    until = ss.effective_until(vendor)
    days_left = None if until is None else max(0, math.ceil((until - now).total_seconds() / 86400))
    gateways = WifiGateway.query.filter_by(vendor_id=vendor.id).order_by(WifiGateway.id).all()
    counts = {st: n for st, n in db.session.query(WifiVoucher.status, db.func.count()).filter_by(
        vendor_id=vendor.id).group_by(WifiVoucher.status)}
    totals = {k: 0 for k in ('HELD', 'SETTLED', 'REFUNDED', 'CONFLICT')}
    for st, amt in db.session.query(WifiPurchase.status, db.func.coalesce(
            db.func.sum(WifiPurchase.amount_gkach), 0)).filter_by(vendor_id=vendor.id).group_by(
            WifiPurchase.status):
        totals[st] = int(amt)
    return {
        'vendor': vendor, 'state': access['state'], 'state_label': _STATE_LABEL.get(access['state'], access['state']),
        'can_sell': access['can_sell'], 'days_left': days_left,
        'next_billing': until, 'trial': vs.trial_status(vendor),
        'balance': GkachService.get_balance(user.whatsapp),
        'price': get_policy('subscription_price_gkach'),
        'gateways': [{'name': g.name, 'uid': g.gateway_uid, 'status': gateway_status(g, now),
                      'seen': ago(g.last_seen_at, now)} for g in gateways],
        'routers': gs.router_summary(vendor.id),
        'packages': WifiPackage.query.filter_by(vendor_id=vendor.id).order_by(WifiPackage.id).all(),
        'voucher_counts': {k: counts.get(k, 0) for k in ('UNUSED', 'REDEEMED', 'REVOKED')},
        'payment_totals': totals, 'renew_key': uuid.uuid4().hex,
    }


def _admin_context():
    now = vs.utcnow()
    by_status = {st: n for st, n in db.session.query(WifiVendor.status, db.func.count()).group_by(
        WifiVendor.status)}
    gws = WifiGateway.query.all()
    return {'vendors_total': sum(by_status.values()), 'vendors_active': by_status.get('ACTIVE', 0),
            'vendors_suspended': by_status.get('SUSPENDED', 0), 'gateways_total': len(gws),
            'gateways_online': sum(gateway_status(g, now) == 'ONLINE' for g in gws)}


def build_zone_context(user):
    ctx = {'authenticated': bool(user), 'vendor': None, 'purchases': [], 'admin': None,
           'trial_days': get_policy('trial_days'), 'price': get_policy('subscription_price_gkach')}
    if not user:
        return ctx
    vendor = WifiVendor.query.filter_by(user_id=user.id).first()
    if vendor is not None:
        ctx.update(_vendor_context(user, vendor))
    ctx['purchases'] = WifiPurchase.query.filter_by(buyer_user_id=user.id).order_by(
        WifiPurchase.id.desc()).limit(10).all()
    if getattr(user, 'is_admin', False):
        ctx['admin'] = _admin_context()
    return ctx


@wifi_ui_bp.get('/zone')
def zone():
    user = current_user if current_user.is_authenticated else None
    return render_template('wifi/zone.html', **build_zone_context(user))


@wifi_ui_bp.post('/zone/register')
@login_required
def zone_register():
    try:
        v = vs.register_vendor(current_user, request.form.get('business_name'), ip=request.remote_addr)
        trial = vs.trial_status(v)
        flash('Byenveni! Kont vandè ou kreye.' + (
            f" Ou gen {get_policy('trial_days')} jou gratis." if trial['state'] == 'ACTIVE' else ''),
            'success')
    except vs.VendorError as e:
        db.session.rollback()
        flash(str(e), 'error')
    return redirect(url_for('wifi_ui.zone'))


@wifi_ui_bp.post('/zone/renew')
@login_required
def zone_renew():
    vendor = WifiVendor.query.filter_by(user_id=current_user.id).first()
    if vendor is None:
        flash('Ou poko vandè Wi-Fi.', 'error')
        return redirect(url_for('wifi_ui.zone'))
    try:
        out = ss.renew_subscription(vendor, request.form.get('key'), ip=request.remote_addr,
                                    actor_user_id=current_user.id)
        flash(f"Abònman renouvle: {out['amount_gkach']} GKach. Aktif jiska {out['period_end'][:10]}.",
              'success')
    except ss.InsufficientFunds:
        flash('Balans GKach ou pa sifi pou renouvle abònman an.', 'error')
    except ss.SubscriptionError as e:
        flash(str(e), 'error')
    return redirect(url_for('wifi_ui.zone'))
