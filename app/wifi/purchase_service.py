"""Customers buy packages with GKach; gateways deliver them with signed tickets.

Money safety (same pattern as the SELL escrow):
  * the buyer is debited, the purchase row and the signed ticket are created in ONE
    transaction; a retry with the same idempotency key returns the same ticket;
  * the vendor is credited only when the gateway reports the ticket REDEEMED
    (compare-and-set HELD -> SETTLED, so a replayed event pays once);
  * never redeemed -> refunded after ticket expiry + grace (compare-and-set
    HELD -> REFUNDED, so it refunds once);
  * the gateway never confirms or fabricates a payment: payment exists only here.
"""
import base64
import ipaddress
import json
import re
import secrets
import uuid
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from app import db
from app.models.gkach_transaction import GkachTransaction
from app.services.gkach_service import GkachService
from app.utils.validators import ValidationError
from app.wifi import signing
from app.wifi import subscription_service as ss
from app.wifi.models import (
    GATEWAY_ENROLLED, PURCHASE_CONFLICT, PURCHASE_HELD, PURCHASE_REFUNDED, PURCHASE_SETTLED,
    WifiGateway, WifiPackage, WifiPurchase, WifiUsageRecord, WifiVendor,
)
from app.wifi.policy import get_policy
from app.wifi.vendor_service import audit, utcnow

_KEY_RE = re.compile(r'^[A-Za-z0-9_\-]{8,64}$')
_TAG_RE = re.compile(r'^[0-9a-f]{32}$')
_TID_RE = re.compile(r'^tk_[0-9a-f]{16}$')
_PRIVATE_SUFFIXES = ('.lan', '.local', '.home.arpa', '.internal', '.localdomain')


class PurchaseError(Exception):
    def __init__(self, msg, status=400):
        super().__init__(msg)
        self.status = status


def validate_portal_url(url):
    """The ticket is handed to this URL, so it must be a LAN address: a public host
    would let someone harvest tickets. Returns the normalised URL or raises."""
    try:
        u = urlsplit(str(url or '').strip())
        host = u.hostname
        port = u.port
    except ValueError:
        raise PurchaseError('invalid portal URL')
    if u.scheme not in ('http', 'https') or not host or u.username or u.password \
            or u.query or u.fragment or u.path not in ('', '/'):
        raise PurchaseError('portal URL must be http(s)://host[:port] with no path or credentials')
    private = False
    try:
        ip = ipaddress.ip_address(host)
        private = ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        private = host == 'localhost' or host.endswith(_PRIVATE_SUFFIXES)
    if not private:
        raise PurchaseError('portal URL must be a private/LAN address')
    return f'{u.scheme}://{host}' + (f':{port}' if port else '')


def _b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b'=').decode()


def make_ticket(gw, pkg, device_tag, tid, now, exp):
    payload = {'v': 1, 'tid': tid, 'gw': gw.gateway_uid, 'dt': device_tag,
               'iat': int(now.timestamp()), 'exp': int(exp.timestamp()),
               'pk': {'n': pkg.name[:40], 'dur': pkg.duration_minutes, 'mb': pkg.data_mb,
                      'dn': pkg.down_kbps, 'up': pkg.up_kbps, 'md': pkg.max_devices}}
    body = _b64u(json.dumps(payload, separators=(',', ':'), sort_keys=True).encode())
    return body + '.' + _b64u(signing.sign_bytes(body.encode()))


def _epoch(dt):
    return int(dt.replace(tzinfo=__import__('datetime').timezone.utc).timestamp())


def purchase_dict(p, with_ticket=False):
    d = {'id': p.id, 'status': p.status, 'package': p.package_name, 'amount_gkach': p.amount_gkach,
         'duration_minutes': p.duration_minutes, 'ticket_id': p.ticket_id,
         'ticket_expires_at': p.ticket_expires_at.isoformat() + 'Z',
         'created_at': p.created_at.isoformat() if p.created_at else None}
    if with_ticket:
        d['ticket'] = p.ticket
    return d


def purchase_package(buyer, gateway_uid, package_id, device_tag, idempotency_key):
    if not isinstance(idempotency_key, str) or not _KEY_RE.match(idempotency_key):
        raise PurchaseError('Idempotency key must be 8-64 chars [A-Za-z0-9_-]')
    if not isinstance(device_tag, str) or not _TAG_RE.match(device_tag):
        raise PurchaseError('invalid device tag')
    gw = WifiGateway.query.filter_by(gateway_uid=str(gateway_uid or '')).first()
    if gw is None or gw.status != GATEWAY_ENROLLED:
        raise PurchaseError('Unknown or inactive gateway', 404)
    vendor = db.session.get(WifiVendor, gw.vendor_id)

    existing = WifiPurchase.query.filter_by(buyer_user_id=buyer.id,
                                            idempotency_key=idempotency_key).first()
    if existing is not None:                         # retry/double-click: same ticket, no new charge
        if (existing.gateway_id, existing.package_id, existing.device_tag) != (
                gw.id, package_id, device_tag):
            raise PurchaseError('Idempotency key already used for a different purchase', 409)
        return existing, True

    if not ss.access_state(vendor)['can_sell']:
        raise PurchaseError('This network is not selling right now', 503)
    pkg = WifiPackage.query.filter_by(id=package_id, vendor_id=vendor.id).first() \
        if isinstance(package_id, int) and not isinstance(package_id, bool) else None
    if pkg is None or not pkg.is_active or pkg.price_gkach <= 0:
        raise PurchaseError('Package not available', 404)
    if buyer.id == vendor.user_id:
        raise PurchaseError('You cannot buy from your own network', 400)
    if not gw.portal_url:
        raise PurchaseError('This gateway has not registered its portal yet', 409)

    now = utcnow()
    exp = now + timedelta(minutes=get_policy('ticket_valid_minutes'))
    tid = 'tk_' + secrets.token_hex(8)
    ref = str(uuid.uuid4())
    price = pkg.price_gkach
    try:
        GkachService.deduct_balance(
            buyer.whatsapp, price, f'Wi-Fi {vendor.vendor_uid} {pkg.name} ref={ref}',
            'wifi_purchase_hold', _commit=False)
    except ValidationError as e:
        db.session.rollback()
        raise PurchaseError(str(e), 402)
    ledger = GkachTransaction.query.filter(
        GkachTransaction.user_whatsapp == buyer.whatsapp,
        GkachTransaction.transaction_type == 'wifi_purchase_hold',
        GkachTransaction.description.like(f'%ref={ref}')).one()
    p = WifiPurchase(vendor_id=vendor.id, gateway_id=gw.id, package_id=pkg.id,
                     buyer_user_id=buyer.id, idempotency_key=idempotency_key,
                     amount_gkach=price, package_name=pkg.name,
                     duration_minutes=pkg.duration_minutes, status=PURCHASE_HELD,
                     ticket_id=tid, ticket=make_ticket(gw, pkg, device_tag, tid, now, exp),
                     device_tag=device_tag, ticket_expires_at=exp,
                     ledger_transaction_id=ledger.transaction_id)
    db.session.add(p)
    audit('purchase.created', vendor.id, buyer.id, f'{tid} {price} GKach gw={gw.gateway_uid}')
    try:
        db.session.commit()                          # debit + purchase + ticket, atomically
    except IntegrityError:
        db.session.rollback()                        # debit rolled back with it
        again = WifiPurchase.query.filter_by(buyer_user_id=buyer.id,
                                             idempotency_key=idempotency_key).first()
        if again is not None:
            return again, True
        raise PurchaseError('Could not complete the purchase, please retry', 409)
    GkachService._invalidate_balance_cache(buyer.whatsapp)
    return p, False


def apply_ticket_redeemed(gw, event_id, payload):
    """Gateway says the ticket was redeemed: release the held funds to the vendor, once."""
    tid = payload.get('ticket_id')
    if not isinstance(tid, str) or not _TID_RE.match(tid):
        audit('purchase.event_rejected', gw.vendor_id, None, f'bad ticket id gw={gw.gateway_uid}')
        return 'REJECTED'
    p = WifiPurchase.query.filter_by(vendor_id=gw.vendor_id, gateway_id=gw.id,
                                     ticket_id=tid).first()
    if p is None:                                    # unknown / another gateway's / another vendor's
        audit('purchase.event_rejected', gw.vendor_id, None,
              f'unknown ticket {tid} gw={gw.gateway_uid}')
        return 'REJECTED'
    n = db.session.execute(
        update(WifiPurchase).where(WifiPurchase.id == p.id, WifiPurchase.status == PURCHASE_HELD)
        .values(status=PURCHASE_SETTLED, settled_at=utcnow())).rowcount
    if n == 1:
        vendor = db.session.get(WifiVendor, p.vendor_id)
        GkachService.add_balance(vendor.user.whatsapp, p.amount_gkach,
                                 f'Vant Wi-Fi {p.ticket_id} ({p.package_name})', 'wifi_sale',
                                 _commit=False)
        audit('purchase.settled', gw.vendor_id, None, f'{tid} {p.amount_gkach} GKach')
        GkachService._invalidate_balance_cache(vendor.user.whatsapp)
        return 'SETTLED'
    db.session.refresh(p)
    if p.status == PURCHASE_REFUNDED:                # delivered after the refund: flag, never pay twice
        p.status = PURCHASE_CONFLICT
        audit('purchase.conflict', gw.vendor_id, None, f'{tid} redeemed after refund')
        return 'CONFLICT'
    return 'DUPLICATE'


def refund_expired_purchases(now=None):
    """Refund purchases never redeemed (ticket expiry + grace). Safe to run repeatedly."""
    now = now or utcnow()
    cutoff = now - timedelta(hours=get_policy('purchase_refund_grace_hours'))
    ids = [r[0] for r in db.session.query(WifiPurchase.id).filter(
        WifiPurchase.status == PURCHASE_HELD, WifiPurchase.ticket_expires_at < cutoff)]
    done = 0
    for pid in ids:
        try:
            n = db.session.execute(
                update(WifiPurchase).where(WifiPurchase.id == pid, WifiPurchase.status == PURCHASE_HELD)
                .values(status=PURCHASE_REFUNDED, refunded_at=now)).rowcount
            if n != 1:
                db.session.rollback()
                continue
            p = db.session.get(WifiPurchase, pid)
            db.session.refresh(p)
            from app.models.user import User
            buyer = db.session.get(User, p.buyer_user_id)
            GkachService.add_balance(buyer.whatsapp, p.amount_gkach,
                                     f'Rembousman Wi-Fi {p.ticket_id} (pa livre)', 'wifi_refund',
                                     _commit=False)
            audit('purchase.refunded', p.vendor_id, None, f'{p.ticket_id} {p.amount_gkach} GKach')
            db.session.commit()
            GkachService._invalidate_balance_cache(buyer.whatsapp)
            done += 1
        except Exception:
            db.session.rollback()
    return done


# --------------------------------- usage ------------------------------------
_SOURCES = ('voucher', 'free', 'purchase')
_MAX_BYTES = 10 ** 13


def apply_usage(gw, event_id, payload):
    src, ref = payload.get('source'), payload.get('ref')
    down, up = payload.get('bytes_down'), payload.get('bytes_up')
    ok = (src in _SOURCES and isinstance(ref, str) and 1 <= len(ref) <= 40
          and all(isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= _MAX_BYTES
                  for v in (down, up)))
    if not ok:
        audit('usage.rejected', gw.vendor_id, None, f'bad usage payload gw={gw.gateway_uid}')
        return 'REJECTED'
    try:
        end = datetime.fromisoformat(str(payload.get('period_end')).replace('Z', '+00:00')).replace(tzinfo=None)
    except ValueError:
        end = utcnow()
    db.session.add(WifiUsageRecord(vendor_id=gw.vendor_id, gateway_id=gw.id, event_id=event_id,
                                   source=src, ref=ref, bytes_down=down, bytes_up=up, period_end=end))
    return 'OK'
