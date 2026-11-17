"""Gateway enrollment, signed-request authentication, idempotent event sync.

Authentication model (outbound-only from the gateway):
  canonical = METHOD \n PATH \n TIMESTAMP \n NONCE \n sha256(body)
  signature = Ed25519(gateway_private_key, canonical)
The timestamp bounds replay to a short window; the nonce table closes it.
"""
import base64
import binascii
import hashlib
import json
import re
import secrets
import time
import uuid
from datetime import datetime, timedelta
from functools import wraps

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from flask import g, jsonify, request
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from app import db
from app.wifi import subscription_service as ss
from app.wifi.models import (
    GATEWAY_ENROLLED, GATEWAY_REVOKED, GATEWAY_SUSPENDED,
    WifiGateway, WifiGatewayEnrollment, WifiGatewayNonce, WifiOfflineEvent,
    WifiRouter, WifiSyncLog, WifiVendor, ROUTER_CAPABILITIES,
)
from app.wifi.policy import get_policy
from app.wifi.vendor_service import audit, utcnow

MAX_SKEW_SECONDS = 300
MAX_BODY_BYTES = 256 * 1024
MAX_BATCH = 200
MAX_EVENT_PAYLOAD = 16 * 1024
EVENT_TYPES = {'session.started', 'session.ended', 'voucher.redeemed', 'ticket.redeemed',
               'usage.recorded', 'payment.pending', 'gateway.event'}
_NONCE_RE = re.compile(r'^[A-Za-z0-9_\-]{16,64}$')
_UID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')


class GatewayError(Exception):
    def __init__(self, msg, status=400):
        super().__init__(msg)
        self.status = status


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def canonical(method, path, ts, nonce, body):
    return '\n'.join([method.upper(), path, str(ts), nonce,
                      hashlib.sha256(body).hexdigest()]).encode()


# ------------------------------- enrollment --------------------------------
def create_enrollment_token(vendor, name, actor_user_id=None, ip=None):
    if not ss.access_state(vendor)['can_sell']:
        raise GatewayError('Subscription inactive: renew before adding a gateway', 402)
    name = (name or '').strip()
    if not (2 <= len(name) <= 80):
        raise GatewayError('Gateway name must be 2-80 characters')
    active = WifiGateway.query.filter(WifiGateway.vendor_id == vendor.id,
                                      WifiGateway.status != GATEWAY_REVOKED).count()
    if active >= get_policy('max_gateways_per_vendor'):
        raise GatewayError('Gateway limit reached for this vendor', 409)
    token = 'uwz1_' + secrets.token_urlsafe(32)
    expires = utcnow() + timedelta(minutes=get_policy('enrollment_token_minutes'))
    db.session.add(WifiGatewayEnrollment(
        vendor_id=vendor.id, token_hash=hash_token(token), name=name,
        expires_at=expires, created_by_user_id=actor_user_id))
    audit('gateway.token_created', vendor.id, actor_user_id, name, ip)
    db.session.commit()
    return token, expires          # the token is shown ONCE; only its hash is stored


def _parse_public_key(b64):
    try:
        raw = base64.b64decode(b64, validate=True)
        if len(raw) != 32:
            raise ValueError('wrong length')
        Ed25519PublicKey.from_public_bytes(raw)
    except (ValueError, binascii.Error, TypeError):
        raise GatewayError('Invalid Ed25519 public key')
    return base64.b64encode(raw).decode()


def enroll_gateway(token, public_key_b64, agent_version=None, ip=None):
    pub = _parse_public_key(public_key_b64)
    enr = WifiGatewayEnrollment.query.filter_by(token_hash=hash_token(token or '')).first()
    # One generic error for unknown / used / expired: no oracle for attackers.
    if enr is None or enr.used_at is not None or enr.expires_at <= utcnow():
        raise GatewayError('Invalid or expired enrollment token', 401)
    if WifiGateway.query.filter_by(public_key=pub).first():
        raise GatewayError('This key is already enrolled', 409)
    vendor = db.session.get(WifiVendor, enr.vendor_id)
    gw = WifiGateway(vendor_id=vendor.id, gateway_uid='gw_' + secrets.token_hex(8),
                     name=enr.name, public_key=pub, enrolled_at=utcnow(),
                     agent_version=(agent_version or '')[:32] or None, last_ip=ip)
    db.session.add(gw)
    db.session.flush()
    # Atomic single-use: only one concurrent enrollment can flip used_at.
    res = db.session.execute(
        update(WifiGatewayEnrollment)
        .where(WifiGatewayEnrollment.id == enr.id, WifiGatewayEnrollment.used_at.is_(None))
        .values(used_at=utcnow(), gateway_id=gw.id))
    if res.rowcount != 1:
        db.session.rollback()
        raise GatewayError('Invalid or expired enrollment token', 401)
    audit('gateway.enrolled', vendor.id, None, gw.gateway_uid, ip)
    db.session.commit()
    return gw, vendor


# --------------------------- request authentication -------------------------
def gateway_signed(f):
    """Authenticate a gateway by Ed25519 signature; bind the tenant to ``g``."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            _authenticate()
        except GatewayError as e:
            return jsonify(error=str(e)), e.status
        return f(*args, **kwargs)
    return wrapper


def _authenticate():
    h = request.headers
    uid, ts, nonce, sig = (h.get('X-UWZ-Gateway'), h.get('X-UWZ-Timestamp'),
                           h.get('X-UWZ-Nonce'), h.get('X-UWZ-Signature'))
    if not (uid and ts and nonce and sig):
        raise GatewayError('Missing signature headers', 401)
    if request.content_length and request.content_length > MAX_BODY_BYTES:
        raise GatewayError('Body too large', 413)
    body = request.get_data(cache=True)
    if len(body) > MAX_BODY_BYTES:
        raise GatewayError('Body too large', 413)
    try:
        ts_i = int(ts)
    except ValueError:
        raise GatewayError('Bad timestamp', 401)
    if abs(time.time() - ts_i) > MAX_SKEW_SECONDS:
        raise GatewayError('Timestamp outside allowed window', 401)
    if not _NONCE_RE.match(nonce):
        raise GatewayError('Bad nonce', 401)
    gw = WifiGateway.query.filter_by(gateway_uid=uid).first()
    if gw is None:
        raise GatewayError('Authentication failed', 401)
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(gw.public_key)).verify(
            base64.b64decode(sig), canonical(request.method, request.path, ts_i, nonce, body))
    except (InvalidSignature, binascii.Error, ValueError):
        raise GatewayError('Authentication failed', 401)
    # Signature is valid: only now may we spend a nonce row (no DoS by strangers).
    try:
        with db.session.begin_nested():
            db.session.add(WifiGatewayNonce(gateway_id=gw.id, nonce=nonce))
            db.session.flush()
    except IntegrityError:
        raise GatewayError('Replayed request', 401)
    if gw.status in (GATEWAY_REVOKED, GATEWAY_SUSPENDED):
        db.session.commit()
        raise GatewayError(f'Gateway {gw.status.lower()}', 403)
    gw.last_seen_at = utcnow()
    gw.last_ip = request.remote_addr
    db.session.commit()
    g.wifi_gateway = gw
    g.wifi_vendor_id = gw.vendor_id            # tenant bound from the KEY, never from input
    g.wifi_vendor = db.session.get(WifiVendor, gw.vendor_id)


def purge_old_nonces(older_than_hours=24):
    cutoff = utcnow() - timedelta(hours=older_than_hours)
    n = WifiGatewayNonce.query.filter(WifiGatewayNonce.created_at < cutoff).delete()
    db.session.commit()
    return n


# ------------------------------ heartbeat / sync -----------------------------
def register_portal_url(gw, url):
    """Store the gateway's LAN portal URL (validated: tickets are handed to it)."""
    from app.wifi.purchase_service import PurchaseError, validate_portal_url
    try:
        gw.portal_url = validate_portal_url(url)
    except PurchaseError:
        return False
    return True


def heartbeat_payload(gw, vendor):
    return {'server_time': utcnow().isoformat() + 'Z', 'server_epoch': int(time.time()),
            'gateway': {'uid': gw.gateway_uid, 'status': gw.status},
            'vendor': {'uid': vendor.vendor_uid, 'status': vendor.status},
            'access': ss.access_state(vendor),
            'license': __import__('app.wifi.license_service', fromlist=['x']).safe_issue(gw, vendor)}


def _validate_event(ev):
    if not isinstance(ev, dict):
        return 'not an object'
    if not isinstance(ev.get('event_id'), str) or not _UID_RE.match(ev['event_id']):
        return 'bad event_id'
    if not isinstance(ev.get('seq'), int) or isinstance(ev['seq'], bool) or ev['seq'] < 0:
        return 'bad seq'
    if ev.get('type') not in EVENT_TYPES:
        return 'unknown type'
    if not isinstance(ev.get('payload'), dict):
        return 'bad payload'
    if len(json.dumps(ev['payload'], separators=(',', ':'))) > MAX_EVENT_PAYLOAD:
        return 'payload too large'
    return None


def _parse_dt(v):
    try:
        return datetime.fromisoformat(v.replace('Z', '+00:00')).replace(tzinfo=None)
    except Exception:
        return None


def ingest_events(gw, events):
    """Idempotent: re-sending an event_id is acknowledged, never stored twice."""
    if not isinstance(events, list) or len(events) > MAX_BATCH:
        raise GatewayError(f'events must be a list of at most {MAX_BATCH}')
    acked, rejected, accepted, dups = [], [], 0, 0
    for ev in events:
        err = _validate_event(ev)
        if err:
            rejected.append({'event_id': ev.get('event_id') if isinstance(ev, dict) else None,
                             'reason': err})
            continue
        try:
            with db.session.begin_nested():
                db.session.add(WifiOfflineEvent(
                    vendor_id=gw.vendor_id,            # from the gateway row, not the payload
                    gateway_id=gw.id, event_id=ev['event_id'], seq=ev['seq'],
                    event_type=ev['type'],
                    payload=json.dumps(ev['payload'], separators=(',', ':')),
                    gateway_created_at=_parse_dt(ev.get('created_at') or '')))
                db.session.flush()
            accepted += 1
            if ev['type'] in ('voucher.redeemed', 'ticket.redeemed', 'usage.recorded', 'gateway.event'):
                _process_business_event(gw, ev)
        except IntegrityError:
            dups += 1
        acked.append(ev['event_id'])
    db.session.add(WifiSyncLog(vendor_id=gw.vendor_id, gateway_id=gw.id,
                               received=len(events), accepted=accepted,
                               duplicates=dups, rejected=len(rejected)))
    db.session.commit()
    return {'acked': acked, 'rejected': rejected, 'accepted': accepted, 'duplicates': dups}


# ------------------------------ router inventory ----------------------------
MAX_ROUTERS = 50
_REF_RE = re.compile(r'^[A-Za-z0-9_\-]{1,40}$')
_STATUSES = ('ONLINE', 'OFFLINE', 'UNSUPPORTED')


def sync_routers(gw, routers):
    """Replace-set: the gateway reports the FULL router list it manages."""
    if not isinstance(routers, list) or len(routers) > MAX_ROUTERS:
        raise GatewayError(f'routers must be a list of at most {MAX_ROUTERS}')
    now, seen = utcnow(), set()
    for r in routers:
        if not isinstance(r, dict) or not _REF_RE.match(str(r.get('ref', ''))):
            raise GatewayError('invalid router entry')
        ref = r['ref']
        if ref in seen:
            raise GatewayError('duplicate router ref')
        seen.add(ref)
        status = r.get('status')
        if status not in _STATUSES:
            raise GatewayError('invalid router status')
        caps = [c for c in (r.get('capabilities') or []) if c in ROUTER_CAPABILITIES]
        row = WifiRouter.query.filter_by(gateway_id=gw.id, router_ref=ref).first()
        if row is None:
            row = WifiRouter(vendor_id=gw.vendor_id, gateway_id=gw.id, router_ref=ref)
            db.session.add(row)
        row.kind = str(r.get('kind', 'generic'))[:20]
        row.vendor_label = str(r.get('vendor', ''))[:40]
        row.model = str(r.get('model', ''))[:80]
        row.firmware = str(r.get('firmware', ''))[:80]
        row.status = status
        row.support_level = 'unsupported' if r.get('support_level') == 'unsupported' else 'implemented'
        row.hardware_verified = bool(r.get('hardware_verified'))
        row.capabilities = json.dumps(caps)
        row.last_error = (str(r['error'])[:200] if r.get('error') else None)
        row.last_report_at = now
    for row in WifiRouter.query.filter_by(gateway_id=gw.id):
        if row.router_ref not in seen:
            db.session.delete(row)
    db.session.commit()
    return {'routers': len(seen)}


def router_summary(vendor_id):
    rows = WifiRouter.query.filter_by(vendor_id=vendor_id).all()
    return {'total': len(rows),
            'online': sum(r.status == 'ONLINE' for r in rows),
            'offline': sum(r.status == 'OFFLINE' for r in rows),
            'unsupported': sum(r.status == 'UNSUPPORTED' for r in rows)}


def _process_business_event(gw, ev):
    """Business processing never fails the sync: the raw event is already stored."""
    from app.wifi import license_service as lsv
    from app.wifi import purchase_service as psv
    from app.wifi import voucher_service as vsv
    handler = {'gateway.event': lsv.apply_gateway_event, 'voucher.redeemed': vsv.apply_redemption,
               'ticket.redeemed': psv.apply_ticket_redeemed,
               'usage.recorded': psv.apply_usage}[ev['type']]
    try:
        with db.session.begin_nested():
            handler(gw, ev['event_id'], ev['payload'])
            WifiOfflineEvent.query.filter_by(gateway_id=gw.id, event_id=ev['event_id']).update(
                {'processed_at': utcnow()})
    except Exception:
        audit(f"{ev['type']}.error", gw.vendor_id, None, f'gw={gw.gateway_uid}')
