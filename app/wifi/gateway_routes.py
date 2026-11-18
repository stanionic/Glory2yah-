"""Machine-to-machine endpoints for gateways (signature auth, CSRF-exempt)."""
from flask import Blueprint, g, jsonify, request

from app import csrf, limiter
from app.wifi import gateway_service as gs
from app.wifi.signing import SigningKeyMissing, cloud_public_key_b64

gateway_bp = Blueprint('wifi_gateway', __name__, url_prefix='/wifi/gateway')
csrf.exempt(gateway_bp)


@gateway_bp.post('/enroll')
@limiter.limit('60 per minute')
def enroll():
    data = request.get_json(silent=True) or {}
    try:
        cloud_pub = cloud_public_key_b64()
        gw, vendor = gs.enroll_gateway(data.get('token'), data.get('public_key'),
                                       data.get('agent_version'), ip=request.remote_addr)
    except SigningKeyMissing:
        return jsonify(error='Cloud signing key not configured'), 503
    except gs.GatewayError as e:
        return jsonify(error=str(e)), e.status
    return jsonify(gateway_uid=gw.gateway_uid, vendor_uid=vendor.vendor_uid,
                   cloud_public_key=cloud_pub), 201


@gateway_bp.post('/heartbeat')
@gs.gateway_signed
def heartbeat():
    from app import db
    from app.wifi import license_service as lsv
    data = request.get_json(silent=True) or {}
    if isinstance(data, dict):
        if data.get('portal_url'):
            gs.register_portal_url(g.wifi_gateway, data['portal_url'])
        lsv.record_clock(g.wifi_gateway, data.get('clock'))
    lsv.track_state(g.wifi_gateway, g.wifi_vendor)          # notify once per lapse/restore
    db.session.commit()
    return jsonify(gs.heartbeat_payload(g.wifi_gateway, g.wifi_vendor))


@gateway_bp.post('/sync')
@gs.gateway_signed
def sync():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error='JSON object required'), 400
    try:
        return jsonify(gs.ingest_events(g.wifi_gateway, data.get('events')))
    except gs.GatewayError as e:
        return jsonify(error=str(e)), e.status


@gateway_bp.post('/routers')
@gs.gateway_signed
def routers():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error='JSON object required'), 400
    try:
        return jsonify(gs.sync_routers(g.wifi_gateway, data.get('routers')))
    except gs.GatewayError as e:
        return jsonify(error=str(e)), e.status


@gateway_bp.post('/sync-policy')
@gs.gateway_signed
def sync_policy():
    from app.wifi import voucher_service as vsv
    data = request.get_json(silent=True) or {}
    cursor = data.get('cursor', 0)
    if isinstance(cursor, bool) or not isinstance(cursor, int) or cursor < 0:
        return jsonify(error='cursor must be a non-negative integer'), 400
    return jsonify(vsv.build_policy(g.wifi_gateway, g.wifi_vendor, cursor))
