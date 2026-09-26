"""Offline-first Jere Biznis blueprint.

The browser is the local store for the admin device.  This integration exposes
the module UI plus a management API (vitrines + co-admin roles).  It does not
create a second Flask app or database inside the main application.
"""
import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Blueprint, abort, jsonify, render_template, request
from flask_login import login_required, current_user
from app import db
from app.models.jere_biznis import (
    JereBiznisAdmin,
    JereBiznisLandingPage,
    JereBiznisPayment,
    JereBiznisSubscription,
    JereBiznisSyncOperation,
)
from app.services.gkach_service import GkachService
from app.utils.validators import ValidationError

_MODULE_ROOT = Path(__file__).resolve().parents[2] / "Jere Biznis"

jere_biznis_web = Blueprint(
    "jere_biznis_web",
    __name__,
    template_folder=str(_MODULE_ROOT / "templates"),
    static_folder=str(_MODULE_ROOT / "static"),
    static_url_path="/assets",
)
jere_biznis_api = Blueprint("jere_biznis_api", __name__)

# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------
JB_PRICE_GKACH = 500
JB_TRIAL_DAYS = 30
ALLOWED_TYPES = {"school", "store", "church", "organization", "other"}

TYPE_LABELS = {
    "school": "Lekòl",
    "store": "Magazen",
    "church": "Legliz",
    "organization": "Òganizasyon",
    "other": "Biznis",
}


# ---------------------------------------------------------------------------
# API errors (JSON, scoped to this blueprint only)
# ---------------------------------------------------------------------------
class JBForbidden(Exception):
    pass


class JBNotFound(Exception):
    pass


@jere_biznis_api.errorhandler(JBNotFound)
def _jb_not_found(_e):
    return jsonify(error="Vitrin sa a pa egziste."), 404


@jere_biznis_api.errorhandler(JBForbidden)
def _jb_forbidden(_e):
    return jsonify(error="Ou pa gen dwa aksè sou vitrin sa a."), 403


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _slugify(value):
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "biznis"


def _unique_slug(base_slug):
    candidate = base_slug
    suffix = 2
    while JereBiznisLandingPage.query.filter_by(slug=candidate).first():
        candidate = f"{base_slug}-{suffix}"
        suffix += 1
    return candidate


def _checksum(payload):
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _as_utc(dt):
    """SQLite returns naive datetimes even for timezone=True columns;
    normalize them to UTC-aware so comparisons never crash."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _add_months(dt, months):
    """Add months to a datetime, clamping the day to the month length."""
    import calendar

    total = (dt.month - 1) + int(months)
    year = dt.year + total // 12
    month = total % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def _get_or_create_subscription(user_id, create=False):
    """Return the user's subscription row. When `create` is True and no row
    exists yet, lazily start the 30-day free trial (first vitrine)."""
    sub = JereBiznisSubscription.query.filter_by(user_id=str(user_id)).first()
    if sub is None and create:
        now = datetime.now(timezone.utc)
        sub = JereBiznisSubscription(
            user_id=str(user_id),
            status=JereBiznisSubscription.STATUS_TRIAL,
            monthly_price_gkach=JB_PRICE_GKACH,
            trial_start=now,
            trial_end=now + timedelta(days=JB_TRIAL_DAYS),
        )
        db.session.add(sub)
        db.session.flush()
    return sub


def _page_admin_role(page, user_id):
    """Role of a user on a page. Ownership wins, so vitrines created before
    the jb_admins table existed remain fully usable."""
    if str(page.owner_user_id) == str(user_id):
        return JereBiznisAdmin.ROLE_OWNER
    row = JereBiznisAdmin.query.filter_by(
        landing_page_id=page.id, user_id=str(user_id), active=True
    ).first()
    return row.role if row else None


def _require_page(pid, user_id):
    page = db.session.get(JereBiznisLandingPage, int(pid))
    if page is None:
        raise JBNotFound()
    role = _page_admin_role(page, user_id)
    if role is None:
        raise JBForbidden()
    return page, role


def _my_pages(user_id):
    owned = JereBiznisLandingPage.query.filter_by(owner_user_id=user_id).all()
    seen = {p.id for p in owned}
    co_rows = JereBiznisAdmin.query.filter_by(
        user_id=user_id, role=JereBiznisAdmin.ROLE_CO_ADMIN, active=True
    ).all()
    pages = list(owned)
    for row in co_rows:
        if row.landing_page_id in seen:
            continue
        page = db.session.get(JereBiznisLandingPage, row.landing_page_id)
        if page is not None:
            pages.append(page)
            seen.add(page.id)
    return pages


def _page_detail(page, user_id):
    co_count = JereBiznisAdmin.query.filter_by(
        landing_page_id=page.id, role=JereBiznisAdmin.ROLE_CO_ADMIN, active=True
    ).count()
    return {
        "id": page.id,
        "business_name": page.business_name,
        "business_type": page.business_type,
        "business_type_label": TYPE_LABELS.get(page.business_type, page.business_type),
        "slug": page.slug,
        "url": f"/jere-biznis/site/{page.slug}",
        "description": page.description or "",
        "phone": page.phone or "",
        "address": page.address or "",
        "published": bool(page.published),
        "created_at": page.created_at.isoformat() if page.created_at else None,
        "role": _page_admin_role(page, user_id),
        "admins_count": 1 + co_count,
    }


def _admins_list(page):
    rows = JereBiznisAdmin.query.filter_by(
        landing_page_id=page.id, active=True
    ).order_by(JereBiznisAdmin.id.asc()).all()
    return [row.to_dict() for row in rows]


def _resolve_target_user(data):
    from app.models.user import User

    uid = data.get("user_id")
    if uid is not None:
        try:
            user = db.session.get(User, int(uid))
        except (ValueError, TypeError):
            user = None
        return user if (user and user.is_active) else None

    pseudo = str(data.get("pseudo", "") or "").strip()
    if pseudo:
        return User.query.filter_by(pseudo=pseudo, is_active=True).first()

    whatsapp = str(data.get("whatsapp", "") or "").strip()
    if whatsapp:
        return User.query.filter_by(whatsapp=whatsapp, is_active=True).first()

    return None


# ---------------------------------------------------------------------------
# Web (admin dashboard + public vitrine)
# ---------------------------------------------------------------------------
@jere_biznis_web.get("/")
@login_required
def dashboard():
    return render_template("dashboard.html", jere_biznis_base="/jere-biznis")


@jere_biznis_web.get("/site/<slug>")
def public_landing_page(slug):
    page = JereBiznisLandingPage.query.filter_by(slug=slug, published=True).first()
    if not page:
        abort(404)
    return render_template("landing_page.html", page=page)


# ---------------------------------------------------------------------------
# Status (computed reminder, never trusted from the client)
# ---------------------------------------------------------------------------
@jere_biznis_api.get("/status")
@login_required
def status():
    mine = _my_pages(str(current_user.id))
    sub = _get_or_create_subscription(str(current_user.id))
    if sub is not None:
        reminder = sub.reminder(datetime.now(timezone.utc))
    else:
        reminder = {"required": False, "status": "NO_PAGE", "days_remaining": 0}
    return jsonify(
        status="OFFLINE_READY",
        institution_id=current_user.id,
        monthly_price_gkach=JB_PRICE_GKACH,
        local_store="IndexedDB",
        sync_ready=True,
        reminder=reminder,
        landing_pages_count=len(mine),
    )


@jere_biznis_api.get("/overview")
@login_required
def overview():
    """Return the facts needed by the management workspace."""
    pages = _my_pages(str(current_user.id))
    published = sum(1 for page in pages if page.published)
    admins = sum(
        JereBiznisAdmin.query.filter_by(
            landing_page_id=page.id, active=True
        ).count()
        for page in pages
    )
    sub = _get_or_create_subscription(str(current_user.id))
    now = datetime.now(timezone.utc)
    return jsonify(
        business_count=len(pages),
        published_count=published,
        team_count=admins,
        subscription_status=sub.compute_status(now) if sub else "NO_PAGE",
        recent_pages=[_page_detail(page, str(current_user.id)) for page in pages[:5]],
    )


# ---------------------------------------------------------------------------
# Subscription: 500 Gkach/month - server-side price, idempotent payments
# ---------------------------------------------------------------------------
def _subscription_payload(sub, now):
    return {
        "monthly_price_gkach": sub.monthly_price_gkach or JB_PRICE_GKACH,
        "status": sub.compute_status(now),
        "trial_start": _as_utc(sub.trial_start).isoformat() if sub.trial_start else None,
        "trial_end": _as_utc(sub.trial_end).isoformat() if sub.trial_end else None,
        "expiration": _as_utc(sub.expiration).isoformat() if sub.expiration else None,
        "reminder": sub.reminder(now),
    }


@jere_biznis_api.get("/subscription")
@login_required
def get_subscription():
    sub = _get_or_create_subscription(str(current_user.id))
    now = datetime.now(timezone.utc)
    balance = GkachService.get_balance(getattr(current_user, "whatsapp", None))
    if sub is None:
        return jsonify(
            monthly_price_gkach=JB_PRICE_GKACH,
            status="NO_PAGE",
            trial_start=None,
            trial_end=None,
            expiration=None,
            reminder={"required": False, "status": "NO_PAGE", "days_remaining": 0},
            gkach_balance=balance,
        )
    sub.last_verified_at = now
    db.session.commit()
    data = _subscription_payload(sub, now)
    data["gkach_balance"] = balance
    return jsonify(data)


@jere_biznis_api.post("/subscription/quote")
@login_required
def subscription_quote():
    data = request.get_json(silent=True) or {}
    try:
        months = int(data.get("months"))
    except (TypeError, ValueError):
        return jsonify(error="Mois dwe yon nonb ant 1 ak 120."), 400
    if months < 1 or months > 120:
        return jsonify(error="Mois dwe yon nonb ant 1 ak 120."), 400
    return jsonify(
        months=months,
        monthly_price_gkach=JB_PRICE_GKACH,
        amount_gkach=months * JB_PRICE_GKACH,
    )


@jere_biznis_api.post("/subscription/pay")
@login_required
def subscription_pay():
    data = request.get_json(silent=True) or {}
    try:
        months = int(data.get("months"))
    except (TypeError, ValueError):
        return jsonify(error="Mois dwe yon nonb ant 1 ak 120."), 400
    idem = str(data.get("idempotency_key", "") or "").strip()
    if months < 1 or months > 120:
        return jsonify(error="Mois dwe yon nonb ant 1 ak 120."), 400
    if not idem:
        return jsonify(error="idempotency_key obligatwa."), 400

    # Idempotency / replay protection - never trust the client.
    previous = JereBiznisPayment.query.filter_by(idempotency_key=idem).first()
    if previous is not None:
        return jsonify(
            status="already_processed",
            transaction_id=previous.transaction_id,
            months=previous.months,
            amount_gkach=previous.amount_gkach,
        )

    sub = _get_or_create_subscription(str(current_user.id), create=True)
    now = datetime.now(timezone.utc)
    amount = months * (sub.monthly_price_gkach or JB_PRICE_GKACH)

    whatsapp = getattr(current_user, "whatsapp", None)
    if not whatsapp:
        return jsonify(error="Pa gen kont Gkach pou kont sa a."), 400
    try:
        GkachService.deduct_balance(
            whatsapp,
            amount,
            f"Jere Biznis: {months} mois x {sub.monthly_price_gkach or JB_PRICE_GKACH} Gkach",
        )
    except (ValueError, ValidationError) as e:
        db.session.rollback()
        return jsonify(
            error=f"Balans Gkach ou pa sufizan oswa kont Gkach pa jwenn. ({e})"
        ), 400

    # Extension stacks on the current expiration (or trial end / now).
    exp = _as_utc(sub.expiration)
    trial_end = _as_utc(sub.trial_end)
    if exp and exp > now:
        base = exp
    elif trial_end and trial_end > now:
        base = trial_end
    else:
        base = now
    sub.expiration = _add_months(base, months)
    sub.subscription_start = sub.subscription_start or now
    sub.status = JereBiznisSubscription.STATUS_ACTIVE
    sub.last_verified_at = now
    payment = JereBiznisPayment(
        user_id=str(current_user.id),
        transaction_id=str(data.get("wallet_transaction_id") or f"jb-{uuid.uuid4()}"),
        idempotency_key=idem,
        months=months,
        monthly_price_gkach=sub.monthly_price_gkach or JB_PRICE_GKACH,
        amount_gkach=amount,
    )
    db.session.add(payment)
    db.session.commit()
    return jsonify(
        status="success",
        months=months,
        amount_gkach=amount,
        transaction_id=payment.transaction_id,
        expiration=_as_utc(sub.expiration).isoformat(),
        gkach_balance=GkachService.get_balance(whatsapp),
    ), 201


# ---------------------------------------------------------------------------
# Vitrines (landing pages) management
# ---------------------------------------------------------------------------
@jere_biznis_api.get("/landing-pages")
@login_required
def list_landing_pages():
    pages = _my_pages(str(current_user.id))
    pages.sort(
        key=lambda p: _as_utc(p.created_at)
        or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return jsonify([_page_detail(p, str(current_user.id)) for p in pages])


@jere_biznis_api.get("/landing-pages/<int:pid>")
@login_required
def get_landing_page(pid):
    page, _role = _require_page(pid, str(current_user.id))
    data = _page_detail(page, str(current_user.id))
    data["admins"] = _admins_list(page)
    return jsonify(data)


@jere_biznis_api.post("/landing-pages")
@login_required
def create_landing_page():
    data = request.get_json(silent=True) or {}
    business_name = str(data.get("business_name", "")).strip()
    business_type = str(data.get("business_type", "")).strip().lower()
    if not business_name or business_type not in ALLOWED_TYPES:
        return jsonify(error="Non biznis la ak yon kalite valid obligatwa."), 400

    page = JereBiznisLandingPage(
        owner_user_id=str(current_user.id),
        business_name=business_name[:160],
        business_type=business_type,
        slug=_unique_slug(_slugify(business_name)),
        description=str(data.get("description", "") or "")[:1000].strip(),
        phone=str(data.get("phone", "") or "")[:40].strip(),
        address=str(data.get("address", "") or "")[:255].strip(),
    )
    db.session.add(page)
    db.session.flush()
    # The creator automatically becomes the OWNER (auto-admin).
    db.session.add(
        JereBiznisAdmin(
            landing_page_id=page.id,
            user_id=str(current_user.id),
            role=JereBiznisAdmin.ROLE_OWNER,
            active=True,
        )
    )
    # The 30-day free trial starts with the first vitrine.
    _get_or_create_subscription(str(current_user.id), create=True)
    db.session.commit()
    return jsonify(_page_detail(page, str(current_user.id))), 201


@jere_biznis_api.put("/landing-pages/<int:pid>")
@login_required
def update_landing_page(pid):
    page, _role = _require_page(pid, str(current_user.id))
    data = request.get_json(silent=True) or {}
    business_name = str(data.get("business_name", page.business_name)).strip()
    business_type = str(data.get("business_type", page.business_type)).strip().lower()
    if not business_name or business_type not in ALLOWED_TYPES:
        return jsonify(error="Non biznis la ak yon kalite valid obligatwa."), 400

    page.business_name = business_name[:160]
    page.business_type = business_type
    page.description = str(data.get("description", page.description or ""))[:1000].strip()
    page.phone = str(data.get("phone", page.phone or ""))[:40].strip()
    page.address = str(data.get("address", page.address or ""))[:255].strip()
    db.session.commit()
    return jsonify(_page_detail(page, str(current_user.id)))


@jere_biznis_api.patch("/landing-pages/<int:pid>")
@login_required
def patch_landing_page(pid):
    page, _role = _require_page(pid, str(current_user.id))
    data = request.get_json(silent=True) or {}
    if "published" in data:
        page.published = bool(data["published"])
    db.session.commit()
    return jsonify(_page_detail(page, str(current_user.id)))


@jere_biznis_api.delete("/landing-pages/<int:pid>")
@login_required
def delete_landing_page(pid):
    page, role = _require_page(pid, str(current_user.id))
    if role != JereBiznisAdmin.ROLE_OWNER:
        return jsonify(error="Se sèlman mèt biznis la ki ka elimine vitrin lan."), 403
    JereBiznisAdmin.query.filter_by(landing_page_id=page.id).delete()
    db.session.delete(page)
    db.session.commit()
    return jsonify(success=True, deleted=pid)


# ---------------------------------------------------------------------------
# Co-admin management (OWNER only)
# ---------------------------------------------------------------------------
@jere_biznis_api.get("/landing-pages/<int:pid>/admins")
@login_required
def list_admins(pid):
    page, _role = _require_page(pid, str(current_user.id))
    return jsonify(_admins_list(page))


@jere_biznis_api.post("/landing-pages/<int:pid>/admins")
@login_required
def add_admin(pid):
    page, role = _require_page(pid, str(current_user.id))
    if role != JereBiznisAdmin.ROLE_OWNER:
        return jsonify(error="Se sèlman mèt biznis la ki ka ajoute ko-admin."), 403

    data = request.get_json(silent=True) or {}
    target = _resolve_target_user(data)
    if target is None:
        return jsonify(error="Nou pa jwenn itilizatè sa a sou Glory2YahPub."), 404

    uid = str(target.id)
    if uid == str(current_user.id):
        return jsonify(error="Ou se deja mèt biznis la."), 400

    existing = JereBiznisAdmin.query.filter_by(
        landing_page_id=page.id, user_id=uid
    ).first()
    if existing:
        if existing.role == JereBiznisAdmin.ROLE_OWNER:
            return jsonify(error="Itilizatè sa a se mèt biznis la deja."), 400
        if existing.active:
            return jsonify(error="Itilizatè sa a se ko-admin deja."), 409
        existing.active = True  # restore a previously revoked co-admin
        existing.role = JereBiznisAdmin.ROLE_CO_ADMIN
    else:
        db.session.add(
            JereBiznisAdmin(
                landing_page_id=page.id,
                user_id=uid,
                role=JereBiznisAdmin.ROLE_CO_ADMIN,
                active=True,
            )
        )
    db.session.commit()
    return jsonify(_admins_list(page)), 201


@jere_biznis_api.delete("/landing-pages/<int:pid>/admins/<int:uid>")
@login_required
def remove_admin(pid, uid):
    page, role = _require_page(pid, str(current_user.id))
    if role != JereBiznisAdmin.ROLE_OWNER:
        return jsonify(error="Se sèlman mèt biznis la ki ka retire ko-admin."), 403
    if str(page.owner_user_id) == str(uid):
        return jsonify(error="Ou pa ka retire mèt biznis la."), 400

    row = JereBiznisAdmin.query.filter_by(
        landing_page_id=page.id, user_id=str(uid), active=True
    ).first()
    if not row or row.role != JereBiznisAdmin.ROLE_CO_ADMIN:
        return jsonify(error="Ko-admin sa a pa egziste."), 404
    row.active = False
    db.session.commit()
    return jsonify(success=True)


# ---------------------------------------------------------------------------
# Sync (offline first - unchanged)
# ---------------------------------------------------------------------------
@jere_biznis_api.post("/sync/push")
@login_required
def sync_push():
    operations = (request.get_json(silent=True) or {}).get("operations", [])
    accepted = []
    duplicates = []
    for operation in operations:
        operation_id = str(operation.get("operation_id", ""))
        payload = operation.get("payload")
        if not operation_id or payload is None:
            return jsonify(error="operation_id and payload are required"), 400
        if operation.get("checksum") != _checksum(payload):
            return jsonify(error=f"checksum mismatch: {operation_id}"), 400
        existing = JereBiznisSyncOperation.query.filter_by(
            operation_id=operation_id
        ).first()
        if existing:
            if existing.admin_user_id != str(current_user.id):
                return jsonify(error="operation belongs to another admin"), 403
            duplicates.append(operation_id)
            continue
        db.session.add(
            JereBiznisSyncOperation(
                operation_id=operation_id,
                admin_user_id=str(current_user.id),
                payload=json.dumps(payload, sort_keys=True),
                checksum=operation["checksum"],
            )
        )
        accepted.append(operation_id)
    db.session.commit()
    return jsonify(accepted=accepted, duplicates=duplicates)


@jere_biznis_api.get("/sync/pull")
@login_required
def sync_pull():
    rows = JereBiznisSyncOperation.query.filter_by(
        admin_user_id=str(current_user.id)
    ).order_by(JereBiznisSyncOperation.id.asc()).all()
    return jsonify(
        [
            {
                "operation_id": row.operation_id,
                "payload": row.payload_object(),
                "checksum": row.checksum,
            }
            for row in rows
        ]
    )