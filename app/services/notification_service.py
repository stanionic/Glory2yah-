"""
Notification Service Layer
Handles WhatsApp link generation and user notifications
"""
import logging
import os
import time
import urllib.parse
import threading
from flask import url_for, current_app

logger = logging.getLogger(__name__)

# Master switch for WhatsApp admin alerts. Set ADMIN_WHATSAPP_ALERTS=0 (or
# false/no/off) in .env to silence them; enabled by default. Sending still
# requires CALLMEBOT_APIKEY (see _send_whatsapp_alert).
_ALERT_THROTTLE_LOCK = threading.Lock()
_ALERT_LAST_SENT = {}


def _alerts_enabled():
    val = (os.environ.get('ADMIN_WHATSAPP_ALERTS', '1') or '1').strip().lower()
    return val not in ('0', 'false', 'no', 'off', '')


# Admin number that receives every approval alert. Overridable through
# ADMIN_WHATSAPP (kept in sync with the rest of the app / the QR login card).
DEFAULT_ADMIN_WHATSAPP = '+50942882076'


def _admin_whatsapp(digits_only=True):
    """Resolve the admin destination number (config → env → default)."""
    raw = ''
    try:
        from flask import current_app
        raw = current_app.config.get('ADMIN_WHATSAPP') or ''
    except Exception:
        raw = ''
    raw = raw or os.environ.get('ADMIN_WHATSAPP') or DEFAULT_ADMIN_WHATSAPP
    raw = str(raw).strip() or DEFAULT_ADMIN_WHATSAPP
    if digits_only:
        return ''.join(c for c in raw if c.isdigit())
    return raw if raw.startswith('+') else '+' + raw


def _http_ok(resp, ok_codes=(200, 201, 202)):
    """Best-effort success check for an HTTP response (never raises)."""
    try:
        return getattr(resp, 'status_code', 0) in ok_codes
    except Exception:
        return False

# ── WhatsApp providers ────────────────────────────────────────────────────────
# Provider chain (first CONFIGURED provider that succeeds wins). Every provider
# is optional: when none is configured the alert is logged + skipped, while the
# in-app admin notification still lands in the admin notification centre.
def _provider_callmebot(phone, message, _req):
    apikey = (os.environ.get('CALLMEBOT_APIKEY') or '').strip()
    if not apikey:
        return None
    url = (
        "https://api.callmebot.com/whatsapp.php"
        f"?phone={phone}&text={urllib.parse.quote(message)}&apikey={apikey}"
    )
    return _req.get(url, timeout=10)


def _provider_ultramsg(phone, message, _req):
    instance = (os.environ.get('ULTRAMSG_INSTANCE_ID') or '').strip()
    token = (os.environ.get('ULTRAMSG_TOKEN') or '').strip()
    if not (instance and token):
        return None
    url = f"https://api.ultramsg.com/{instance}/messages/chat"
    return _req.post(url, data={'token': token, 'to': '+' + phone, 'body': message},
                     timeout=10)


def _provider_cloud_api(phone, message, _req):
    """Meta WhatsApp Cloud API (official Business API)."""
    token = (os.environ.get('WHATSAPP_CLOUD_TOKEN') or '').strip()
    phone_id = (os.environ.get('WHATSAPP_CLOUD_PHONE_ID') or '').strip()
    if not (token and phone_id):
        return None
    url = f"https://graph.facebook.com/v19.0/{phone_id}/messages"
    return _req.post(
        url,
        headers={'Authorization': f'Bearer {token}'},
        json={'messaging_product': 'whatsapp', 'to': phone, 'type': 'text',
              'text': {'preview_url': False, 'body': message}},
        timeout=10,
    )


def _provider_webhook(phone, message, _req):
    """Generic bridge/webhook (n8n, Zapier, Make, self-hosted Baileys gateway…)."""
    hook = (os.environ.get('WHATSAPP_ALERT_WEBHOOK_URL') or '').strip()
    if not hook:
        return None
    return _req.post(hook, json={'to': phone, 'phone': phone, 'text': message,
                                 'message': message, 'channel': 'whatsapp'},
                     timeout=10)


_WHATSAPP_PROVIDERS = (
    ('callmebot', _provider_callmebot),
    ('ultramsg', _provider_ultramsg),
    ('whatsapp_cloud_api', _provider_cloud_api),
    ('webhook', _provider_webhook),
)

# Last provider that accepted a message (diagnostics / admin UI).
_ALERT_LAST_PROVIDER = {'name': None, 'at': None}


def whatsapp_alert_status():
    """Describe the WhatsApp admin-alert configuration (used by the admin UI).

    Returns ``{'enabled': bool, 'phone': '+509…', 'provider': name|None,
    'providers': [...], 'last_provider': name|None}``. Never raises.
    """
    configured = []
    _env = os.environ.get
    if (_env('CALLMEBOT_APIKEY') or '').strip():
        configured.append('callmebot')
    if (_env('ULTRAMSG_INSTANCE_ID') or '').strip() and (_env('ULTRAMSG_TOKEN') or '').strip():
        configured.append('ultramsg')
    if (_env('WHATSAPP_CLOUD_TOKEN') or '').strip() and (_env('WHATSAPP_CLOUD_PHONE_ID') or '').strip():
        configured.append('whatsapp_cloud_api')
    if (_env('WHATSAPP_ALERT_WEBHOOK_URL') or '').strip():
        configured.append('webhook')
    return {
        'enabled': _alerts_enabled(),
        'phone': _admin_whatsapp(digits_only=False),
        'provider': configured[0] if configured else None,
        'providers': configured,
        'last_provider': _ALERT_LAST_PROVIDER.get('name'),
    }



def _send_whatsapp_alert(message: str, phone: str = None):
    """Send a WhatsApp message to the admin number (fire-and-forget).

    Walks the provider chain and returns the name of the provider that accepted
    the message, or ``None`` when no provider is configured / all failed. Every
    failure is swallowed and logged — this function MUST never raise: it runs in
    a daemon thread spawned by :func:`alert_admin`.

    Configure at least ONE provider in `.env`:
      * ``CALLMEBOT_APIKEY``                                   (free, easiest)
        register the number once at
        https://www.callmebot.com/blog/free-api-whatsapp-messages/
      * ``ULTRAMSG_INSTANCE_ID`` + ``ULTRAMSG_TOKEN``           (paid gateway)
      * ``WHATSAPP_CLOUD_TOKEN`` + ``WHATSAPP_CLOUD_PHONE_ID``  (Meta Cloud API)
      * ``WHATSAPP_ALERT_WEBHOOK_URL``                          (any bridge/webhook)
    """
    try:
        import requests as _req
    except Exception as exc:  # requests unavailable → nothing we can do
        logger.warning('WhatsApp alert skipped (requests unavailable): %s', exc)
        return None

    digits = phone or _admin_whatsapp(digits_only=True)

    for name, provider in _WHATSAPP_PROVIDERS:
        try:
            resp = provider(digits, message, _req)
        except Exception as exc:
            logger.warning('WhatsApp alert via %s raised: %s', name, exc)
            continue
        if resp is None:
            continue  # not configured — try the next provider
        if _http_ok(resp):
            logger.info('WhatsApp admin alert sent via %s to +%s', name, digits)
            _ALERT_LAST_PROVIDER['name'] = name
            return name
        logger.warning('WhatsApp alert via %s rejected (HTTP %s)',
                       name, getattr(resp, 'status_code', '?'))

    logger.warning(
        'WhatsApp admin alert NOT delivered to +%s — no provider configured or all '
        'failed. Set CALLMEBOT_APIKEY (or ULTRAMSG_*, WHATSAPP_CLOUD_*, '
        'WHATSAPP_ALERT_WEBHOOK_URL) in .env. The alert is still stored in the '
        'admin notification centre.', digits,
    )
    return None


def alert_admin(message: str, throttle_seconds: int = 0):
    """Fire-and-forget WhatsApp alert to admin. Never blocks the request.

    When throttle_seconds > 0, identical messages sent within that window are
    collapsed to one send — so instrumenting 'every traffic' cannot flood the
    CallMeBot endpoint (it rate-limits aggressively).
    """
    if not _alerts_enabled():
        return
    if throttle_seconds:
        now = time.time()
        with _ALERT_THROTTLE_LOCK:
            last = _ALERT_LAST_SENT.get(message, 0)
            if now - last < throttle_seconds:
                return
            # Opportunistic cleanup so the cache doesn't grow unbounded.
            if len(_ALERT_LAST_SENT) > 500:
                cutoff = now - max(throttle_seconds, 60)
                for k in [k for k, v in _ALERT_LAST_SENT.items() if v < cutoff]:
                    _ALERT_LAST_SENT.pop(k, None)
            _ALERT_LAST_SENT[message] = now
    threading.Thread(target=_send_whatsapp_alert, args=(message,), daemon=True).start()


def admin_event(action: str, detail: str = '', actor: str = '', send_whatsapp: bool = True):
    """Send a consistently-formatted WhatsApp alert for an admin-panel action.

    Produces e.g. '[ADMIN] BLOKE IP — 1.2.3.4 (pa admin509)'. Lightly throttled
    (3s) to guard against double-submits / rapid repeats.

    Some admin-only actions are internal workflow events and should remain in-app
    logs without spamming the WhatsApp admin channel. Pass send_whatsapp=False
    in those cases.
    """
    msg = f'[ADMIN] {action}'
    if detail:
        msg += f' \u2014 {detail}'
    if actor:
        msg += f' (pa {actor})'
    if send_whatsapp:
        alert_admin(msg, throttle_seconds=3)
    return msg


class NotificationService:
    """Service for sending notifications (generating WhatsApp links)"""
    
    ADMIN_WHATSAPP = "+50942882076"
    
    @staticmethod
    def generate_whatsapp_link(phone_number, message=""):
        """Generate WhatsApp wa.me link"""
        if not phone_number:
            return None
            
        # Clean phone number
        clean_number = ''.join(c for c in phone_number if c.isdigit() or c == '+')
        if not clean_number.startswith('+'):
            clean_number = '+' + clean_number
            
        base_url = f"https://wa.me/{clean_number.replace('+', '')}"
        
        if message:
            encoded_message = urllib.parse.quote(message)
            return f"{base_url}?text={encoded_message}"
            
        return base_url

    @staticmethod
    def notify_admin_new_ad(user_whatsapp, ad_id):
        """Notify admin of new ad submission"""
        message = f"Nouvo piblisite soumèt pa {user_whatsapp}. ID: {ad_id}"
        return NotificationService.generate_whatsapp_link(NotificationService.ADMIN_WHATSAPP, message)

    @staticmethod
    def notify_user_ad_status(user_whatsapp, ad_id, status):
        """Notify user when ad status changes"""
        if status == 'approved':
            message = f"Piblisite w la (ID: {ad_id}) apwouve! Li parèt sou platfòm lan kounye a."
        else:
            message = f"Piblisite w la (ID: {ad_id}) rejte. Tanpri kontakte nou pou plis detay."
            
        return NotificationService.generate_whatsapp_link(user_whatsapp, message)

    @staticmethod
    def notify_seller_new_order(seller_whatsapp, buyer_whatsapp, delivery_id, ad_title):
        """Notify seller of new order/delivery request"""
        try:
            update_url = url_for('delivery.view', delivery_id=delivery_id, _external=True)
        except:
            update_url = f"/delivery/view/{delivery_id}"
            
        message = (
            f"🛒 NOUVO DEMANN LIVREZON\n\n"
            f"📦 Piblisite: {ad_title}\n"
            f"👤 Achte pa: {buyer_whatsapp}\n"
            f"🔗 Klike la a pou mete pri livrezon an: {update_url}"
        )
        return NotificationService.generate_whatsapp_link(seller_whatsapp, message)

    @staticmethod
    def notify_buyer_cost_set(buyer_whatsapp, delivery_id, cost, total):
        """Notify buyer when delivery cost is set"""
        try:
            confirm_url = url_for('delivery.view', delivery_id=delivery_id, _external=True)
        except:
            confirm_url = f"/delivery/view/{delivery_id}"
            
        message = (
            f"🚚 PRI LIVREZON METE AJOU\n\n"
            f"Kou livrezon: {cost} Gkach\n"
            f"Total pou peye: {total} Gkach\n"
            f"🔗 Klike la a pou konfime epi peye: {confirm_url}"
        )
        return NotificationService.generate_whatsapp_link(buyer_whatsapp, message)

    @staticmethod
    def notify_admin_gkach_request(user_whatsapp, amount):
        """Notify admin of Gkach request"""
        message = f"Nouvo demann Gkach: {amount} Gkach pou {user_whatsapp}."
        return NotificationService.generate_whatsapp_link(NotificationService.ADMIN_WHATSAPP, message)
