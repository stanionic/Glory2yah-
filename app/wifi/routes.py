"""Vendor-facing and Super Admin routes of the UWZ module."""
from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from app import db
from app.utils.security import admin_required
from app.wifi import gateway_service as gs
from app.wifi import purchase_service as psv
from app.wifi import voucher_service as vsv
from app.wifi import subscription_service as ss
from app.wifi import vendor_service as vs
from app.services.gkach_service import GkachService
from app.wifi.models import (GATEWAY_ENROLLED, GATEWAY_REVOKED, GATEWAY_SUSPENDED,
                             WifiAuditLog, WifiGateway, WifiPackage, WifiRouter, WifiVendor,
                             WifiPurchase, WifiVoucher, WifiVoucherRedemption, VENDOR_STATUSES)
from app.wifi.policy import DEFAULTS, get_policy, set_policy
from app.wifi.tenancy import current_vendor, get_owned, wifi_vendor_required

wifi_bp = Blueprint('wifi', __name__, url_prefix='/wifi')


def _payload():
    return request.get_json(silent=True) or request.form


@wifi_bp.post('/vendor/register')
@login_required
def vendor_register():
    data = _payload()
    try:
        vendor = vs.register_vendor(current_user, data.get('business_name'),
                                    data.get('contact_phone'), ip=request.remote_addr)
    except vs.VendorError as e:
        return jsonify(error=str(e)), 400
    return jsonify(vendor=vendor.to_dict(), trial=vs.trial_status(vendor)), 201


@wifi_bp.get('/vendor/dashboard')
@wifi_vendor_required(allow_inactive=True)
def vendor_dashboard():
    v = current_vendor()
    return jsonify(vendor=v.to_dict(), trial=vs.trial_status(v),
                   access=ss.access_state(v), routers=gs.router_summary(v.id))


@wifi_bp.get('/vendor/subscription')
@wifi_vendor_required(allow_inactive=True)
def vendor_subscription():
    v = current_vendor()
    return jsonify(access=ss.access_state(v), trial=vs.trial_status(v),
                   price_gkach=get_policy('subscription_price_gkach'),
                   period_days=get_policy('subscription_period_days'),
                   balance_gkach=GkachService.get_balance(v.user.whatsapp),
                   history=ss.history(v.id))


@wifi_bp.post('/vendor/subscription/renew')
@wifi_vendor_required(allow_inactive=True)
def vendor_subscription_renew():
    v = current_vendor()
    try:
        out = ss.renew_subscription(v, request.headers.get('Idempotency-Key'),
                                    ip=request.remote_addr, actor_user_id=current_user.id)
    except ss.SubscriptionError as e:
        return jsonify(error=str(e)), e.status_code
    return jsonify(out), (200 if out['replayed'] else 201)


# ---------------- Super Admin ----------------
@wifi_bp.get('/admin/vendors')
@admin_required
def admin_vendors():
    status = request.args.get('status')
    q = WifiVendor.query
    if status in VENDOR_STATUSES:
        q = q.filter_by(status=status)
    return jsonify(vendors=[dict(v.to_dict(), trial=vs.trial_status(v))
                            for v in q.order_by(WifiVendor.id.desc()).limit(200)])


def _admin_action(vendor_id, fn, *args):
    vendor = db.session.get(WifiVendor, vendor_id)
    if vendor is None:
        return jsonify(error='not found'), 404
    try:
        fn(vendor, *args, actor_user_id=current_user.id, ip=request.remote_addr)
    except vs.VendorError as e:
        return jsonify(error=str(e)), 400
    db.session.commit()
    return jsonify(vendor=vendor.to_dict())


@wifi_bp.post('/admin/vendors/<int:vendor_id>/activate')
@admin_required
def admin_activate(vendor_id):
    return _admin_action(vendor_id, vs.activate_vendor)


@wifi_bp.post('/admin/vendors/<int:vendor_id>/suspend')
@admin_required
def admin_suspend(vendor_id):
    return _admin_action(vendor_id, vs.suspend_vendor, _payload().get('reason'))


@wifi_bp.post('/admin/vendors/<int:vendor_id>/reject')
@admin_required
def admin_reject(vendor_id):
    return _admin_action(vendor_id, vs.reject_vendor, _payload().get('reason'))


@wifi_bp.get('/admin/policy')
@admin_required
def admin_policy_get():
    return jsonify({k: get_policy(k) for k in DEFAULTS})


@wifi_bp.post('/admin/policy')
@admin_required
def admin_policy_set():
    out = {}
    try:
        for k, val in (_payload() or {}).items():
            out[k] = set_policy(k, val)
    except (KeyError, ValueError) as e:
        db.session.rollback()
        return jsonify(error=f'invalid policy: {e}'), 400
    vs.audit('policy.changed', actor_user_id=current_user.id, detail=str(out),
             ip=request.remote_addr)
    db.session.commit()
    return jsonify(out)


@wifi_bp.get('/admin/audit')
@admin_required
def admin_audit():
    rows = WifiAuditLog.query.order_by(WifiAuditLog.id.desc()).limit(200)
    return jsonify(logs=[{'at': r.created_at.isoformat(), 'vendor_id': r.vendor_id,
                          'actor': r.actor_user_id, 'action': r.action,
                          'detail': r.detail} for r in rows])


@wifi_bp.get('/admin/vendors/<int:vendor_id>/subscription-history')
@admin_required
def admin_subscription_history(vendor_id):
    v = db.session.get(WifiVendor, vendor_id)
    if v is None:
        return jsonify(error='not found'), 404
    return jsonify(vendor=v.to_dict(), access=ss.access_state(v),
                   history=ss.history(v.id, limit=200))


@wifi_bp.get('/admin/subscriptions')
@admin_required
def admin_subscriptions():
    want = request.args.get('state')
    out = []
    for v in WifiVendor.query.order_by(WifiVendor.id.desc()).limit(500):
        a = ss.access_state(v)
        if want and a['state'] != want:
            continue
        out.append({'vendor': v.to_dict(), 'access': a})
    return jsonify(subscriptions=out)


@wifi_bp.post('/admin/jobs/trial-warnings')
@admin_required
def admin_trial_warnings():
    return jsonify(warned=ss.send_trial_warnings())


# ---------------- Gateways (vendor + admin) ----------------
def _gw_dict(gw):
    return {'id': gw.id, 'gateway_uid': gw.gateway_uid, 'name': gw.name,
            'status': gw.status, 'last_seen_at': gw.last_seen_at.isoformat() if gw.last_seen_at else None,
            'agent_version': gw.agent_version}


@wifi_bp.post('/vendor/gateways/enrollment-tokens')
@wifi_vendor_required()
def vendor_gateway_token():
    v = current_vendor()
    try:
        token, expires = gs.create_enrollment_token(
            v, _payload().get('name'), actor_user_id=current_user.id, ip=request.remote_addr)
    except gs.GatewayError as e:
        return jsonify(error=str(e)), e.status
    return jsonify(token=token, expires_at=expires.isoformat(),
                   note='Shown once. Use it within the validity window.'), 201


@wifi_bp.get('/vendor/gateways')
@wifi_vendor_required(allow_inactive=True)
def vendor_gateways():
    rows = WifiGateway.query.filter_by(vendor_id=current_vendor().id).order_by(WifiGateway.id)
    return jsonify(gateways=[_gw_dict(g_) for g_ in rows])


@wifi_bp.post('/vendor/gateways/<int:gateway_id>/revoke')
@wifi_vendor_required(allow_inactive=True)
def vendor_gateway_revoke(gateway_id):
    gw = get_owned(WifiGateway, gateway_id, current_vendor().id)
    gw.status = GATEWAY_REVOKED
    vs.audit('gateway.revoked', gw.vendor_id, current_user.id, gw.gateway_uid,
             request.remote_addr)
    db.session.commit()
    return jsonify(_gw_dict(gw))


@wifi_bp.get('/admin/gateways')
@admin_required
def admin_gateways():
    rows = WifiGateway.query.order_by(WifiGateway.id.desc()).limit(500)
    return jsonify(gateways=[dict(_gw_dict(g_), vendor_id=g_.vendor_id,
                                  clock_skew_s=g_.last_clock_skew_s,
                                  clock_rollbacks=g_.clock_rollbacks or 0,
                                  license_state=g_.last_license_state) for g_ in rows])


@wifi_bp.post('/admin/gateways/<int:gateway_id>/<action>')
@admin_required
def admin_gateway_action(gateway_id, action):
    target = {'suspend': GATEWAY_SUSPENDED, 'reactivate': GATEWAY_ENROLLED,
              'revoke': GATEWAY_REVOKED}.get(action)
    gw = db.session.get(WifiGateway, gateway_id)
    if target is None or gw is None:
        return jsonify(error='not found'), 404
    if gw.status == GATEWAY_REVOKED:
        return jsonify(error='revoked gateways are final'), 409
    gw.status = target
    vs.audit(f'gateway.{action}', gw.vendor_id, current_user.id, gw.gateway_uid,
             request.remote_addr)
    db.session.commit()
    return jsonify(_gw_dict(gw))


def _router_dict(r):
    import json as _json
    return {'id': r.id, 'ref': r.router_ref, 'kind': r.kind, 'vendor': r.vendor_label,
            'model': r.model, 'firmware': r.firmware, 'status': r.status,
            'support_level': r.support_level, 'hardware_verified': r.hardware_verified,
            'capabilities': _json.loads(r.capabilities or '[]'), 'error': r.last_error,
            'last_report_at': r.last_report_at.isoformat() if r.last_report_at else None}


@wifi_bp.get('/vendor/routers')
@wifi_vendor_required(allow_inactive=True)
def vendor_routers():
    v = current_vendor()
    rows = WifiRouter.query.filter_by(vendor_id=v.id).order_by(WifiRouter.id)
    return jsonify(summary=gs.router_summary(v.id), routers=[_router_dict(r) for r in rows])


@wifi_bp.get('/admin/routers')
@admin_required
def admin_routers():
    rows = WifiRouter.query.order_by(WifiRouter.id.desc()).limit(500)
    return jsonify(routers=[dict(_router_dict(r), vendor_id=r.vendor_id) for r in rows])


# ---------------- Packages, portal settings, vouchers (vendor) ----------------
def _vsv(fn, *a, **k):
    try:
        return fn(*a, **k), None
    except vsv.VoucherError as e:
        db.session.rollback()
        return None, (jsonify(error=str(e)), e.status)


@wifi_bp.post('/vendor/packages')
@wifi_vendor_required()
def vendor_package_create():
    pkg, err = _vsv(vsv.create_package, current_vendor(), _payload() or {}, current_user.id)
    return err or (jsonify(vsv.package_dict(pkg)), 201)


@wifi_bp.get('/vendor/packages')
@wifi_vendor_required(allow_inactive=True)
def vendor_package_list():
    rows = WifiPackage.query.filter_by(vendor_id=current_vendor().id).order_by(WifiPackage.id)
    return jsonify(packages=[vsv.package_dict(p) for p in rows])


@wifi_bp.patch('/vendor/packages/<int:package_id>')
@wifi_vendor_required()
def vendor_package_update(package_id):
    pkg = get_owned(WifiPackage, package_id, current_vendor().id)
    _, err = _vsv(vsv.update_package, pkg, _payload() or {}, current_user.id)
    return err or jsonify(vsv.package_dict(pkg))


@wifi_bp.get('/vendor/portal')
@wifi_vendor_required(allow_inactive=True)
def vendor_portal_get():
    cfg = vsv.get_portal(current_vendor())
    db.session.commit()
    return jsonify(vsv.portal_dict(cfg))


@wifi_bp.put('/vendor/portal')
@wifi_vendor_required()
def vendor_portal_update():
    cfg, err = _vsv(vsv.update_portal, current_vendor(), _payload() or {}, current_user.id)
    return err or jsonify(vsv.portal_dict(cfg))


@wifi_bp.post('/vendor/vouchers/generate')
@wifi_vendor_required()
def vendor_voucher_generate():
    v, data = current_vendor(), _payload() or {}
    pkg = get_owned(WifiPackage, data.get('package_id'), v.id) if isinstance(
        data.get('package_id'), int) else None
    gw = get_owned(WifiGateway, data.get('gateway_id'), v.id) if isinstance(
        data.get('gateway_id'), int) else None
    if pkg is None or gw is None:
        return jsonify(error='package_id and gateway_id (integers you own) are required'), 400
    res, err = _vsv(vsv.generate_vouchers, v, pkg, gw, data.get('count'),
                    data.get('expires_in_days'), data.get('label'), current_user.id,
                    request.remote_addr)
    if err:
        return err
    batch, codes, expires = res
    resp = jsonify(batch_id=batch, codes=codes, expires_at=expires.isoformat(),
                   note='These codes are shown ONCE and cannot be recovered. Print or save them now.')
    resp.headers['Cache-Control'] = 'no-store'
    return resp, 201


@wifi_bp.get('/vendor/vouchers')
@wifi_vendor_required(allow_inactive=True)
def vendor_voucher_list():
    q = WifiVoucher.query.filter_by(vendor_id=current_vendor().id)
    if request.args.get('status'):
        q = q.filter_by(status=request.args['status'].upper())
    if request.args.get('batch_id'):
        q = q.filter_by(batch_id=request.args['batch_id'])
    limit = max(1, min(request.args.get('limit', 100, type=int), 500))
    rows = q.order_by(WifiVoucher.id.desc()).limit(limit).all()
    return jsonify(vouchers=[vsv.voucher_dict(x) for x in rows])


@wifi_bp.post('/vendor/vouchers/<int:voucher_id>/revoke')
@wifi_vendor_required()
def vendor_voucher_revoke(voucher_id):
    v = get_owned(WifiVoucher, voucher_id, current_vendor().id)
    _, err = _vsv(vsv.revoke_voucher, v, current_user.id, request.remote_addr)
    return err or jsonify(vsv.voucher_dict(v))


@wifi_bp.get('/vendor/vouchers/<int:voucher_id>/redemptions')
@wifi_vendor_required(allow_inactive=True)
def vendor_voucher_redemptions(voucher_id):
    v = get_owned(WifiVoucher, voucher_id, current_vendor().id)
    rows = WifiVoucherRedemption.query.filter_by(voucher_id=v.id, vendor_id=v.vendor_id).order_by(
        WifiVoucherRedemption.id)
    return jsonify(voucher=vsv.voucher_dict(v), redemptions=[
        {'device': r.device_mac, 'outcome': r.outcome, 'note': r.note,
         'redeemed_at': r.redeemed_at.isoformat() if r.redeemed_at else None,
         'ends_at': r.ends_at.isoformat() if r.ends_at else None} for r in rows])


# ---------------- Customers buy packages with GKach ----------------
def _purchase_response(p, replayed):
    gw = db.session.get(WifiGateway, p.gateway_id)
    resp = jsonify(purchase=psv.purchase_dict(p, with_ticket=True),
                   deliver_to=(gw.portal_url or '') + '/ticket', replayed=replayed)
    resp.headers['Cache-Control'] = 'no-store'
    return resp, (200 if replayed else 201)


@wifi_bp.post('/customer/purchase')
@login_required
def customer_purchase():
    data = _payload() or {}
    key = request.headers.get('Idempotency-Key') or data.get('idempotency_key')
    pid = data.get('package_id')
    try:
        p, replayed = psv.purchase_package(current_user, data.get('gateway_uid'), pid,
                                           data.get('device_tag'), key)
    except psv.PurchaseError as e:
        return jsonify(error=str(e)), e.status
    return _purchase_response(p, replayed)


@wifi_bp.get('/customer/purchases')
@login_required
def customer_purchases():
    rows = WifiPurchase.query.filter_by(buyer_user_id=current_user.id).order_by(
        WifiPurchase.id.desc()).limit(100)
    return jsonify(purchases=[psv.purchase_dict(p) for p in rows])     # never lists tickets


@wifi_bp.get('/vendor/payments')
@wifi_vendor_required(allow_inactive=True)
def vendor_payments():
    v = current_vendor()
    q = WifiPurchase.query.filter_by(vendor_id=v.id)
    if request.args.get('status'):
        q = q.filter_by(status=request.args['status'].upper())
    limit = max(1, min(request.args.get('limit', 100, type=int), 500))
    rows = q.order_by(WifiPurchase.id.desc()).limit(limit).all()
    totals = {st: 0 for st in ('HELD', 'SETTLED', 'REFUNDED', 'CONFLICT')}
    for st, amt in db.session.query(WifiPurchase.status, db.func.coalesce(
            db.func.sum(WifiPurchase.amount_gkach), 0)).filter_by(vendor_id=v.id).group_by(
            WifiPurchase.status):
        totals[st] = int(amt)
    return jsonify(totals_gkach=totals, payments=[
        dict(psv.purchase_dict(p), package_id=p.package_id) for p in rows])


@wifi_bp.post('/admin/jobs/refund-expired-purchases')
@admin_required
def admin_refund_expired():
    return jsonify(refunded=psv.refund_expired_purchases())


_BUY_CSS = ('body{font-family:system-ui,sans-serif;background:#f4f6f5;margin:0}main{max-width:420px;'
            'margin:auto;padding:18px}.card{background:#fff;border-radius:10px;padding:16px}'
            'button{background:#0b6b3a;color:#fff;border:0;border-radius:8px;padding:12px;width:100%;'
            'font-size:16px}.err{background:#fde8e8;padding:10px;border-radius:8px}')
_BUY_PAGE = """<!doctype html><html lang="ht"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Achte Wi-Fi</title>
<style>{{ css }}</style></head><body><main>
{% if error %}<div class="err">{{ error }}</div>{% endif %}
{% if pkg %}<div class="card"><h2>{{ pkg.name }}</h2>
<p>{{ pkg.duration_minutes }} minit · <strong>{{ pkg.price_gkach }} Gkach</strong></p>
<p>Balans ou: {{ balance }} Gkach</p>
<form method="post" action="{{ url_for('wifi.buy_page') }}">
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
<input type="hidden" name="gw" value="{{ gw }}"><input type="hidden" name="pkg" value="{{ pkg.id }}">
<input type="hidden" name="d" value="{{ d }}"><input type="hidden" name="key" value="{{ key }}">
<button type="submit">Peye {{ pkg.price_gkach }} Gkach</button></form></div>{% endif %}
</main></body></html>"""
_HANDOFF_PAGE = """<!doctype html><html lang="ht"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Peman fèt</title>
<style>{{ css }}</style></head><body><main><div class="card"><h2>Peman fèt</h2>
<p>Kounye a nou ap konekte w sou rezo Wi-Fi a.</p>
<form id="f" method="post" action="{{ action }}">
<input type="hidden" name="ticket" value="{{ ticket }}">
<button type="submit">Konekte kounye a</button></form></div></main>
<script>document.getElementById('f').submit()</script></body></html>"""


def _buy_headers(resp):
    resp.headers['Cache-Control'] = 'no-store'
    resp.headers['Referrer-Policy'] = 'no-referrer'
    resp.headers['X-Frame-Options'] = 'DENY'
    return resp


@wifi_bp.route('/buy', methods=['GET', 'POST'])
@login_required
def buy_page():
    """Confirm-and-pay page the customer reaches from the gateway portal. The
    customer's password is typed on Glory2YahPub only; the vendor never sees it."""
    from flask import make_response, render_template_string
    from app.services.gkach_service import GkachService
    import uuid as _uuid
    form = request.form if request.method == 'POST' else request.args
    gw_uid, d = form.get('gw', ''), form.get('d', '')
    try:
        pkg_id = int(form.get('pkg', ''))
    except ValueError:
        pkg_id = None
    gw = WifiGateway.query.filter_by(gateway_uid=gw_uid).first()
    pkg = WifiPackage.query.filter_by(id=pkg_id, vendor_id=gw.vendor_id, is_active=True).first() \
        if gw and pkg_id else None
    if gw is None or pkg is None:
        return _buy_headers(make_response(render_template_string(
            _BUY_PAGE, css=_BUY_CSS, error='Fòfè sa a pa disponib.', pkg=None), 404))
    if request.method == 'GET':
        return _buy_headers(make_response(render_template_string(
            _BUY_PAGE, css=_BUY_CSS, error=None, pkg=pkg, gw=gw_uid, d=d, key=_uuid.uuid4().hex,
            balance=GkachService.get_balance(current_user.whatsapp))))
    try:
        p, _ = psv.purchase_package(current_user, gw_uid, pkg.id, d, form.get('key'))
    except psv.PurchaseError as e:
        return _buy_headers(make_response(render_template_string(
            _BUY_PAGE, css=_BUY_CSS, error=str(e), pkg=pkg, gw=gw_uid, d=d, key=form.get('key'),
            balance=GkachService.get_balance(current_user.whatsapp)), e.status))
    return _buy_headers(make_response(render_template_string(
        _HANDOFF_PAGE, css=_BUY_CSS, action=gw.portal_url + '/ticket', ticket=p.ticket)))
