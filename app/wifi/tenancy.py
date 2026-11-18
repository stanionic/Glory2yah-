"""Strict tenant isolation (service + authorization + persistence layers).

* tenant_query / get_owned: every read is filtered by vendor_id; a foreign id
  is indistinguishable from a missing one (404, no enumeration).
* before_flush guard: inside a vendor request, any tenant-owned row being
  created/modified/deleted with a different vendor_id aborts the transaction.
* wifi_vendor_required: resolves the vendor from the logged-in user only,
  never from a client-supplied vendor_id.
"""
from functools import wraps

from flask import abort, g, jsonify, request
from flask_login import current_user
from sqlalchemy import event
from sqlalchemy.orm import Session

from app import db
from app.wifi.models import WifiVendor, VENDOR_ACTIVE


class TenantViolation(Exception):
    pass


def _is_tenant_model(obj):
    return getattr(obj, '__tenant_scoped__', False)


def tenant_query(model, vendor_id):
    if not getattr(model, '__tenant_scoped__', False):
        raise TypeError(f'{model.__name__} is not tenant scoped')
    return model.query.filter_by(vendor_id=vendor_id)


def get_owned(model, obj_id, vendor_id):
    obj = tenant_query(model, vendor_id).filter_by(id=obj_id).first()
    if obj is None:
        abort(404)
    return obj


@event.listens_for(Session, 'before_flush')
def _tenant_flush_guard(session, flush_context, instances):
    vendor_id = getattr(g, 'wifi_vendor_id', None) if _has_ctx() else None
    if vendor_id is None:
        return  # background/admin/service context: no request tenant bound
    for obj in list(session.new) + list(session.dirty) + list(session.deleted):
        if _is_tenant_model(obj) and getattr(obj, 'vendor_id', None) != vendor_id:
            raise TenantViolation(
                f'{type(obj).__name__} belongs to another tenant')


def _has_ctx():
    try:
        from flask import has_request_context
        return has_request_context()
    except Exception:  # pragma: no cover
        return False


def current_vendor():
    return getattr(g, 'wifi_vendor', None)


def wifi_vendor_required(allow_inactive=False):
    """Authenticated user who owns a vendor account. Binds the tenant to g."""
    def deco(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return jsonify(error='authentication required'), 401
            vendor = WifiVendor.query.filter_by(user_id=current_user.id).first()
            if vendor is None:
                return jsonify(error='not a vendor'), 403
            if not allow_inactive and vendor.status != VENDOR_ACTIVE:
                return jsonify(error='vendor not active', status=vendor.status), 403
            g.wifi_vendor = vendor
            g.wifi_vendor_id = vendor.id
            return f(*args, **kwargs)
        return wrapper
    return deco
