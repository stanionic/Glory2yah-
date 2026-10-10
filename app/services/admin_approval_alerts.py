"""
Admin Approval Alerts — WhatsApp + in-app alerting for every traffic that
lands in an ADMIN APPROVAL queue
===========================================================================

One entry point used by every module that produces work an administrator must
approve before it becomes visible / effective:

    * new ad submitted             → AdService.create_ad()
    * ad edited (re-approval)      → AdService.update_ad()
    * publication-fee proof sent   → main.upload_payment()
    * GKACH recharge request       → gkach.request_gkach()
    * GKACH cash withdrawal        → gkach.withdraw()
    * MENNEN driver enrolment      → mennem.register_driver()
    * event organization signup    → events._register_organization()
    * Bank loan application        → bank.loan_apply()

Two independent delivery channels — neither can ever break the caller:

    1. **WhatsApp push to the admin number** (``ADMIN_WHATSAPP``, default
       ``+50942882076``) through :func:`notification_service.alert_admin`, which
       walks the provider chain (CallMeBot → UltraMsg → WhatsApp Cloud API →
       generic webhook; see ``notification_service._WHATSAPP_PROVIDERS``).
    2. **In-app notification** persisted for every admin user (``User.is_admin``)
       through the existing ``NotificationHub`` + the ``admin_*`` i18n templates.
       This is also the guaranteed fallback: even with no WhatsApp provider
       configured (or WhatsApp down) the alert shows in the admin notification
       centre with the pending item's deep link.

Hard rules
----------
* **Never raises** — a failed alert must never fail the business action
  (mirrors ``NotificationHub`` rule §35).
* **Throttled** per (kind, entity) so double submits / retries cannot flood the
  WhatsApp provider (CallMeBot rate-limits aggressively).
* **No duplicate systems** — reuses ``notification_service`` (WhatsApp) and
  ``NotificationHub`` (in-app/push). Nothing new is invented.
"""
import logging

from app.services.notification_service import (
    alert_admin,
    whatsapp_alert_status,
    _admin_whatsapp,
)

logger = logging.getLogger(__name__)


# ───────────────────────── approval kind registry ─────────────────────────
# kind → how the alert is worded (WhatsApp) + rendered (in-app i18n template)
# `template` MUST exist in app/services/notification_templates.py TEMPLATES.
# `throttle` = seconds of de-duplication for identical alerts (0 = never throttle).
APPROVAL_KINDS = {
    'ad_new': {
        'label': 'NOUVO PIBLISITE',
        'icon': '📢',
        'template': 'admin_new_ad',
        'priority': 'high',
        'url': '/admin/ads',
        'throttle': 5,
    },
    'ad_edited': {
        'label': 'PIBLISITE MODIFYE',
        'icon': '✏️',
        'template': 'admin_ad_edited',
        'priority': 'high',
        'url': '/admin/ads',
        'throttle': 5,
    },
    'ad_payment': {
        'label': 'PREV PEMAN RESEVWA',
        'icon': '💰',
        'template': 'admin_payment',
        'priority': 'high',
        'url': '/admin/ads',
        'throttle': 5,
    },
    'gkach_recharge': {
        'label': 'DEMANN RECHAJ GKACH',
        'icon': '🔋',
        'template': 'admin_recharge_request',
        'priority': 'high',
        'url': '/admin/gkach/manage',
        'throttle': 5,
    },
    'gkach_withdrawal': {
        'label': 'DEMANN RETRIZ',
        'icon': '💸',
        'template': 'admin_withdrawal_request',
        'priority': 'urgent',
        'url': '/admin/gkach/manage',
        'throttle': 5,
    },
    'driver_registration': {
        'label': 'NOUVO CHOFE MENNEN',
        'icon': '🚕',
        'template': 'admin_driver_registration',
        'priority': 'high',
        'url': '/mennenm/admin',
        'throttle': 5,
    },
    'org_registration': {
        'label': 'NOUVO ORGANIZASYON',
        'icon': '⛪',
        'template': 'admin_org_registration',
        'priority': 'normal',
        'url': '/admin/events',
        'throttle': 5,
    },
    'loan_application': {
        'label': 'DEMANN PRE',
        'icon': '🏦',
        'template': 'admin_loan_request',
        'priority': 'high',
        'url': '/admin/bank',
        'throttle': 5,
    },
    'seller_certification': {
        'label': 'DEMANN SETIFIKASYON VANDE',
        'icon': '🏪',
        'template': 'admin_seller_certification',
        'priority': 'normal',
        'url': '/admin/users',
        'throttle': 5,
    },
    'generic': {
        'label': 'APWOBASYON NESESE',
        'icon': '🛎️',
        'template': 'admin_approval_generic',
        'priority': 'high',
        'url': '/admin',
        'throttle': 0,
    },
}


# ───────────────────────────── helpers ─────────────────────────────

def _absolute(path):
    """Turn an app-relative path into an absolute URL (best effort, never raises)."""
    if not path:
        return ''
    if str(path).startswith(('http://', 'https://')):
        return str(path)
    try:
        from flask import current_app, url_for
        base = (current_app.config.get('PUBLIC_BASE_URL')
                or current_app.config.get('BASE_URL')
                or current_app.config.get('SERVER_NAME') or '')
        if base:
            base = str(base).rstrip('/')
            if not base.startswith('http'):
                base = 'https://' + base
            return base + str(path)
        return url_for('main.index', _external=True).rstrip('/') + str(path)
    except Exception:
        return str(path)


def _clean_summary(summary, limit=180):
    text = ' '.join(str(summary or '').split())
    return text if len(text) <= limit else text[:limit - 1] + '…'


def _whatsapp_message(meta, actor='', summary='', detail='', amount=None, url=''):
    """Build the Creole WhatsApp alert body (matches the existing alert style)."""
    lines = [f"[APWOBASYON] {meta['icon']} {meta['label']}"]
    if summary:
        lines.append(_clean_summary(summary))
    if actor:
        lines.append(f"Pa: {actor}")
    if amount is not None:
        lines.append(f"Montan: {amount} GK")
    if detail:
        lines.append(_clean_summary(detail, 220))
    if url:
        lines.append(f"Aksyon: {url}")
    lines.append("(ouvri panno admin pou apwouve oswa rejte)")
    return '\n'.join(lines)


def admin_whatsapp_number():
    """The WhatsApp number that receives every approval alert (E.164 form)."""
    try:
        return _admin_whatsapp(digits_only=False)
    except Exception:
        return '+50942882076'


def _admin_users():
    """Every active admin user that can receive an in-app notification."""
    try:
        from app.models.user import User
        rows = User.query.filter_by(is_admin=True).all()
    except Exception as exc:
        logger.debug('admin lookup failed: %s', exc)
        return []
    return [u for u in rows
            if getattr(u, 'is_active', True) and getattr(u, 'whatsapp', None)]


# ───────────────────────────── core entry point ─────────────────────────────

def alert_approval_required(kind, actor='', summary='', detail='', amount=None,
                            entity_type=None, entity_id=None, url=None,
                            extra=None, throttle_seconds=None, sender_id=None,
                            push=True):
    """Alert every administrator that `kind` traffic needs approval.

    Parameters
    ----------
    kind            : key of :data:`APPROVAL_KINDS` (falls back to 'generic').
    actor           : who triggered it (whatsapp number, pseudo, display name…).
    summary         : one-line description (ad title, driver name, org name…).
    detail          : optional extra context.
    amount          : optional GKACH amount (withdrawals, recharges, loans…).
    entity_type/id  : deep-link target stored on the in-app notification.
    url             : override the registry's admin URL.
    extra           : extra context for the i18n renderer (`{title}`, `{when}`…).
    throttle_seconds: override the registry de-duplication window.
    sender_id       : User.id of the submitter (an admin who submits is skipped).

    Returns the WhatsApp message body (useful for tests / logs). Never raises.
    """
    meta = APPROVAL_KINDS.get(str(kind or '').strip()) or APPROVAL_KINDS['generic']

    if throttle_seconds is None:
        throttle_seconds = meta.get('throttle', 0) or 0

    actor_label = str(actor or 'Yon itilizatè').strip()
    summary = _clean_summary(summary)
    detail = _clean_summary(detail, 220)

    route = url or meta.get('url') or '/admin'
    absolute = _absolute(route)

    message = _whatsapp_message(meta, actor=actor_label, summary=summary,
                                detail=detail, amount=amount, url=absolute)

    # ── channel 1: WhatsApp push to ADMIN_WHATSAPP (+50942882076) ──
    try:
        alert_admin(message, throttle_seconds=throttle_seconds)
    except Exception as exc:
        logger.warning('approval WhatsApp alert failed (kind=%s): %s', kind, exc)

    # ── channel 2: in-app notification for every admin user ──
    try:
        _create_in_app(meta, kind=kind, actor=actor_label, summary=summary,
                       detail=detail, amount=amount, url=absolute,
                       entity_type=entity_type, entity_id=entity_id,
                       extra=extra, sender_id=sender_id, push=push)
    except Exception as exc:
        logger.warning('approval in-app alert failed (kind=%s): %s', kind, exc)

    return message


def _create_in_app(meta, kind, actor, summary, detail, amount, url,
                   entity_type, entity_id, extra, sender_id, push=True):
    """Persist one NotificationHub row per admin user (i18n-rendered)."""
    try:
        from app.services.notification_hub import NotificationHub
    except Exception as exc:
        logger.debug('NotificationHub unavailable: %s', exc)
        return 0

    admins = _admin_users()
    if not admins:
        logger.info('No admin user row found — approval alert sent via WhatsApp only '
                    '(kind=%s).', kind)
        return 0

    ctx = {
        'actor': actor,
        'description': detail or summary or actor,
        'title': summary or detail or '',
        'amount': amount if amount is not None else '',
        'kind': kind,
    }
    if isinstance(extra, dict):
        ctx.update(extra)
    ctx.setdefault('url', url)

    created = 0
    for admin in admins:
        if sender_id and int(getattr(admin, 'id', 0) or 0) == int(sender_id):
            continue  # the admin IS the submitter — no self-alert
        notif = NotificationHub.create(
            recipient_id=admin.id,
            notification_type=meta['template'],
            context=ctx,
            actor_name=actor,
            sender_id=sender_id,
            title=ctx['title'] or None,
            icon=meta['icon'],
            url=url or None,
            category='admin',
            priority=meta['priority'],
            entity_type=entity_type,
            entity_id=entity_id,
            aggregate=False,        # approvals must never be merged away
            push=bool(push),
            realtime=True,
            force=True,             # operational alert → never muted away
        )
        if notif is not None:
            created += 1
    logger.info('Approval alert kind=%s → %s admin notification(s).', kind, created)
    return created


# ═══════════════════ convenience wrappers (used by call sites) ═══════════════════

def alert_ad_awaiting_review(ad, actor=None):
    """New ad submitted → admin must approve/reject it (and verify the fee)."""
    return alert_approval_required(
        'ad_new',
        actor=actor or getattr(ad, 'user_whatsapp', ''),
        summary=f"« {getattr(ad, 'title', '')} » — {getattr(ad, 'ad_type', '')}",
        detail=(f"ID {getattr(ad, 'ad_id', '')} · "
                f"{getattr(ad, 'category', 'other')} · "
                f"pri {getattr(ad, 'price_gkach', 0)} GK · "
                f"statu peman: {getattr(ad, 'payment_status', 'pending')}"),
        entity_type='ad', entity_id=getattr(ad, 'ad_id', None),
        url='/admin/ads',
    )


def alert_ad_edited(ad, actor=None):
    """Ad edited by its owner → back to review."""
    return alert_approval_required(
        'ad_edited',
        actor=actor or getattr(ad, 'user_whatsapp', ''),
        summary=f"« {getattr(ad, 'title', '')} »",
        detail=f"ID {getattr(ad, 'ad_id', '')} — piblisite modifye, re-apwobasyon nesesè",
        entity_type='ad', entity_id=getattr(ad, 'ad_id', None),
        url='/admin/ads',
    )


def alert_ad_payment_proof(ad, filename=None):
    """Publication-fee proof uploaded → admin must verify the payment."""
    return alert_approval_required(
        'ad_payment',
        actor=getattr(ad, 'user_whatsapp', ''),
        summary=f"« {getattr(ad, 'title', '')} »",
        detail=(f"ID {getattr(ad, 'ad_id', '')} · frè {getattr(ad, 'publish_fee_gkach', 0)} GK"
                + (f" · prèv: {filename}" if filename else '')),
        amount=getattr(ad, 'publish_fee_gkach', None),
        entity_type='ad', entity_id=getattr(ad, 'ad_id', None),
        url='/admin/ads',
    )


def alert_recharge_request(user_whatsapp, amount, request_id=None,
                           currency='HTG', payment_method='moncash'):
    """GKACH top-up request → admin must approve the credited amount."""
    return alert_approval_required(
        'gkach_recharge',
        actor=user_whatsapp,
        summary=f"{amount} GK ({currency} · {payment_method})",
        detail=f"Demann rechaj#{(' ' + str(request_id)[:8]) if request_id else ''}",
        amount=amount,
        entity_type='gkach_request', entity_id=request_id,
        url='/admin/gkach/manage',
    )


def alert_withdrawal_request(user_whatsapp, amount, transaction_id=None,
                             payment_method='moncash', payout_details=''):
    """GKACH → cash withdrawal request → admin must approve/reject."""
    return alert_approval_required(
        'gkach_withdrawal',
        actor=user_whatsapp,
        summary=f"Retriz {amount} GK via {payment_method}",
        detail=payout_details or f"Tx {transaction_id or ''}",
        amount=amount,
        entity_type='gkach_transaction', entity_id=transaction_id,
        url='/admin/gkach/manage',
    )


def alert_driver_registration(driver):
    """MENNEN M driver enrolment → admin must verify + activate the driver."""
    name = getattr(driver, 'name', '') or 'Chofè'
    return alert_approval_required(
        'driver_registration',
        actor=getattr(driver, 'whatsapp', ''),
        summary=f"{name} ({getattr(driver, 'city', '') or 'vil enkoni'})",
        detail=(f"Adrès: {getattr(driver, 'address', '')} · "
                f"Tarif baz: {getattr(driver, 'base_fare', '')} GK"),
        entity_type='mennem_driver', entity_id=getattr(driver, 'id', None),
        url='/mennenm/admin',
    )


def alert_organization_registration(org, event=None):
    """Event organization signup → admin confirms or rejects it."""
    org_name = getattr(org, 'org_name', '') or 'Òganizasyon'
    return alert_approval_required(
        'org_registration',
        actor=getattr(org, 'contact_name', '') or getattr(org, 'phone', '') or '',
        summary=f"{org_name} ({getattr(org, 'org_type', '')})",
        detail=(f"Kontak: {getattr(org, 'phone', '') or '—'} · "
                f"Vil: {getattr(org, 'city', '') or '—'}"
                + (f" · Evènman: {getattr(event, 'title', '')}" if event else '')),
        entity_type='event_organization', entity_id=getattr(org, 'id', None),
        url='/admin/events',
    )


def alert_loan_request(loan, product=None, user=None):
    """Bank loan application → admin approves/rejects the loan."""
    amount = getattr(loan, 'amount', None)
    return alert_approval_required(
        'loan_application',
        actor=(getattr(user, 'pseudo', None) or getattr(user, 'whatsapp', None)
               or f"user#{getattr(loan, 'user_id', '')}"),
        summary=f"Prè {amount} GK" + (f" · {getattr(product, 'name', '')}" if product else ''),
        detail=(f"Total pou peye: {getattr(loan, 'total_due', '')} GK"
                + (f" · Objektif: {getattr(loan, 'purpose', '')}" if getattr(loan, 'purpose', '') else '')),
        amount=amount,
        entity_type='loan', entity_id=getattr(loan, 'loan_id', None),
        url='/admin/bank',
    )


def alert_seller_certification(user, notes=''):
    """Seller certification request → admin certifies the seller."""
    return alert_approval_required(
        'seller_certification',
        actor=getattr(user, 'pseudo', None) or getattr(user, 'whatsapp', ''),
        summary=f"{getattr(user, 'name', '') or getattr(user, 'pseudo', '')}",
        detail=notes or f"WhatsApp: {getattr(user, 'whatsapp', '')}",
        entity_type='user', entity_id=getattr(user, 'id', None),
        url='/admin/users',
    )


# ═══════════════════ pending queue overview (admin dashboard) ═══════════════════

def _count(fn, default=0):
    """Run a counting lambda and swallow any failure (missing table, etc.)."""
    try:
        return int(fn() or 0)
    except Exception as exc:
        logger.debug('pending count failed: %s', exc)
        return default


def count_recharge_requests():
    """Pending GKACH recharge requests (stored as JSON on UserGkach)."""
    def _run():
        import json
        from app.models.user_gkach import UserGkach
        total = 0
        for account in UserGkach.query.all():
            raw = getattr(account, 'gkach_requests', None)
            if not raw or raw == '[]':
                continue
            try:
                items = json.loads(raw)
            except Exception:
                continue
            if isinstance(items, list):
                total += sum(1 for it in items
                             if isinstance(it, dict) and it.get('status') == 'pending')
        return total
    return _count(_run)


def pending_approvals_summary():
    """Snapshot of EVERY queue that requires an admin decision.

    Used by the admin dashboard banner + the `/admin/alerts` page. Each value
    degrades to 0 when its module/table is unavailable, so this never raises.
    """
    from app.models.ad import Ad
    from app.models.bank import Loan
    from app.models.events import EventOrganization
    from app.models.mennem_driver import MennemDriver
    from app.services.gkach_service import GkachService

    summary = {
        'ads_under_review': _count(lambda: Ad.query.filter_by(
            admin_status='under_review').count()),
        'ads_payment_pending': _count(lambda: Ad.query.filter(
            Ad.payment_status == 'pending',
            Ad.payment_proof.isnot(None)).count()),
        'ads_rejected': _count(lambda: Ad.query.filter_by(
            admin_status='rejected').count()),
        'withdrawals_pending': _count(
            lambda: len(GkachService.get_pending_withdrawals(limit=1000))),
        'recharges_pending': count_recharge_requests(),
        'drivers_pending': _count(lambda: MennemDriver.query.filter_by(
            is_verified=False, is_active=False).count()),
        'organizations_pending': _count(lambda: EventOrganization.query.filter_by(
            status='pending').count()),
        'loans_pending': _count(lambda: Loan.query.filter_by(
            status='pending').count()),
        'donations_pending': 0,
    }
    summary['total'] = (
        summary['ads_under_review'] + summary['ads_payment_pending']
        + summary['withdrawals_pending'] + summary['recharges_pending']
        + summary['drivers_pending'] + summary['organizations_pending']
        + summary['loans_pending']
    )
    return summary


def send_test_alert(actor='Administratè'):
    """Send a real test alert through BOTH channels (admin 'Test' button).

    Returns ``{'message': str, 'whatsapp': dict, 'delivered': bool}``.
    """
    message = alert_approval_required(
        'generic',
        actor=actor,
        summary='Tès alèt WhatsApp administratè',
        detail='Si ou resevwa mesaj sa a, alèt apwobasyon yo byen konfigire.',
        throttle_seconds=0,
    )
    status = whatsapp_alert_status()
    return {
        'message': message,
        'whatsapp': status,
        'delivered': bool(status.get('providers')),
    }


__all__ = [
    'APPROVAL_KINDS',
    'alert_approval_required',
    'alert_ad_awaiting_review',
    'alert_ad_edited',
    'alert_ad_payment_proof',
    'alert_recharge_request',
    'alert_withdrawal_request',
    'alert_driver_registration',
    'alert_organization_registration',
    'alert_loan_request',
    'alert_seller_certification',
    'pending_approvals_summary',
    'count_recharge_requests',
    'send_test_alert',
    'whatsapp_alert_status',
]


