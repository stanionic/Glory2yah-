"""
OTP Delivery — Multi-Provider Chain
====================================

Tries every configured provider in priority order and returns the first
provider name that successfully delivers the code, or ``None`` when every
attempt fails.

Free-first provider priority
-----------------------------
1. **Textbee** (https://textbee.dev) — truly free SMS gateway that uses
   your own Android phone/SIM as the modem.  No subscription, no credit
   card.  Set TEXTBEE_API_KEY + TEXTBEE_DEVICE_ID in .env.

2. **CallMeBot WhatsApp** — free for the *registered* admin number only
   (the API key is bound to a single number pre-registered with the bot).
   Useful for the signup flow ONLY if the registering number matches the
   admin's.  Skip if CALLMEBOT_APIKEY is not set.
   Register at: https://www.callmebot.com/blog/free-api-whatsapp-messages/

3. **UltraMsg** (paid WhatsApp gateway) — tried when configured.

4. **Meta WhatsApp Cloud API** (official Business API) — tried when
   configured.

5. **Generic Webhook** (n8n / Make / Zapier / Baileys bridge) — tried
   when configured.

6. **Email OTP** — zero-cost fallback when an email address is known for
   the registering user. Requires MAIL_* env vars (SMTP) or just
   MAIL_PROVIDER=console for local dev (logs to stdout).

Environment variables
----------------------
TEXTBEE_API_KEY           — Textbee API key (required for Textbee)
TEXTBEE_DEVICE_ID         — optional; omit to use the default active device
TEXTBEE_BASE_URL          — override for self-hosted instances
                            (default: https://api.textbee.dev/api/v1)
CALLMEBOT_APIKEY          — CallMeBot WhatsApp API key
ULTRAMSG_INSTANCE_ID      — UltraMsg instance
ULTRAMSG_TOKEN            — UltraMsg token
WHATSAPP_CLOUD_TOKEN      — Meta Cloud API bearer token
WHATSAPP_CLOUD_PHONE_ID   — Meta Cloud API phone number ID
WHATSAPP_ALERT_WEBHOOK_URL— Generic bridge webhook
MAIL_PROVIDER             — smtp | console (default: console)
MAIL_SMTP_HOST            — SMTP hostname
MAIL_SMTP_PORT            — SMTP port (default: 587)
MAIL_SMTP_USER            — SMTP username
MAIL_SMTP_PASS            — SMTP password
MAIL_FROM                 — Sender address
"""
import logging
import os
import urllib.parse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _env(key, default=''):
    return (os.environ.get(key) or default).strip()


def _http_ok(resp):
    try:
        return getattr(resp, 'status_code', 0) in (200, 201, 202)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Provider 1: Textbee (free SMS via own Android device)
# ---------------------------------------------------------------------------

def _send_textbee(phone_e164: str, message: str) -> str | None:
    """
    Send via Textbee.  Returns 'textbee' on success, None otherwise.

    API reference: https://textbee.dev/docs
    POST /gateway/devices/{deviceId}/send-sms
    Headers: x-api-key: <key>
    Body: { "recipients": ["+50912345678"], "message": "..." }
    """
    api_key = _env('TEXTBEE_API_KEY')
    if not api_key:
        return None

    base_url = _env('TEXTBEE_BASE_URL', 'https://api.textbee.dev/api/v1')
    device_id = _env('TEXTBEE_DEVICE_ID')

    if device_id:
        url = f'{base_url}/gateway/devices/{device_id}/send-sms'
    else:
        # Without a device_id, Textbee uses the first active device
        url = f'{base_url}/gateway/devices/send-sms'

    try:
        import requests as _req
        resp = _req.post(
            url,
            headers={'x-api-key': api_key, 'Content-Type': 'application/json'},
            json={'recipients': [phone_e164], 'message': message},
            timeout=12,
        )
        body = ''
        try:
            body = resp.text or ''
        except Exception:
            pass

        if _http_ok(resp):
            logger.info('OTP sent via Textbee to %s', phone_e164[:6] + '***')
            return 'textbee'
        else:
            logger.warning(
                'Textbee OTP delivery failed: HTTP %s — %s',
                getattr(resp, 'status_code', '?'), body[:200],
            )
            return None
    except Exception as exc:
        logger.warning('Textbee provider raised: %s', exc)
        return None


# ---------------------------------------------------------------------------
# Provider 2: CallMeBot WhatsApp (free, bound to 1 registered number)
# ---------------------------------------------------------------------------

def _send_callmebot(phone_digits: str, message: str) -> str | None:
    apikey = _env('CALLMEBOT_APIKEY')
    if not apikey:
        return None
    try:
        import requests as _req
        url = (
            'https://api.callmebot.com/whatsapp.php'
            f'?phone={phone_digits}&text={urllib.parse.quote(message)}&apikey={apikey}'
        )
        resp = _req.get(url, timeout=10)
        body = (getattr(resp, 'text', '') or '').upper()
        if _http_ok(resp) and 'QUEUED' in body:
            logger.info('OTP sent via CallMeBot to %s***', phone_digits[:4])
            return 'callmebot'
        logger.warning('CallMeBot OTP not queued: %s', body[:200])
        return None
    except Exception as exc:
        logger.warning('CallMeBot provider raised: %s', exc)
        return None


# ---------------------------------------------------------------------------
# Provider 3: UltraMsg (paid WhatsApp gateway)
# ---------------------------------------------------------------------------

def _send_ultramsg(phone_digits: str, message: str) -> str | None:
    instance = _env('ULTRAMSG_INSTANCE_ID')
    token = _env('ULTRAMSG_TOKEN')
    if not (instance and token):
        return None
    try:
        import requests as _req
        import json as _json
        resp = _req.post(
            f'https://api.ultramsg.com/{instance}/messages/chat',
            data={'token': token, 'to': '+' + phone_digits, 'body': message},
            timeout=10,
        )
        try:
            data = _json.loads(resp.text or '{}')
        except Exception:
            data = {}
        status = str(data.get('status', '') or data.get('result', '') or '').lower()
        if _http_ok(resp) and status not in ('error', 'failure', 'failed') \
                and not data.get('errorMessage') and not data.get('error'):
            logger.info('OTP sent via UltraMsg')
            return 'ultramsg'
        logger.warning('UltraMsg OTP body-error: %s', (resp.text or '')[:200])
        return None
    except Exception as exc:
        logger.warning('UltraMsg provider raised: %s', exc)
        return None


# ---------------------------------------------------------------------------
# Provider 4: Meta WhatsApp Cloud API
# ---------------------------------------------------------------------------

def _send_cloud_api(phone_digits: str, message: str) -> str | None:
    token = _env('WHATSAPP_CLOUD_TOKEN')
    phone_id = _env('WHATSAPP_CLOUD_PHONE_ID')
    if not (token and phone_id):
        return None
    try:
        import requests as _req
        resp = _req.post(
            f'https://graph.facebook.com/v19.0/{phone_id}/messages',
            headers={'Authorization': f'Bearer {token}'},
            json={
                'messaging_product': 'whatsapp',
                'to': phone_digits,
                'type': 'text',
                'text': {'preview_url': False, 'body': message},
            },
            timeout=10,
        )
        if _http_ok(resp):
            logger.info('OTP sent via Meta Cloud API')
            return 'whatsapp_cloud_api'
        logger.warning(
            'Meta Cloud API OTP failed: HTTP %s — %s',
            getattr(resp, 'status_code', '?'), (getattr(resp, 'text', '') or '')[:200],
        )
        return None
    except Exception as exc:
        logger.warning('Meta Cloud API provider raised: %s', exc)
        return None


# ---------------------------------------------------------------------------
# Provider 5: Generic Webhook
# ---------------------------------------------------------------------------

def _send_webhook(phone_digits: str, message: str) -> str | None:
    hook = _env('WHATSAPP_ALERT_WEBHOOK_URL')
    if not hook:
        return None
    try:
        import requests as _req
        resp = _req.post(
            hook,
            json={'to': phone_digits, 'phone': phone_digits,
                  'text': message, 'message': message, 'channel': 'whatsapp'},
            timeout=10,
        )
        if _http_ok(resp):
            logger.info('OTP sent via generic webhook')
            return 'webhook'
        logger.warning(
            'Webhook OTP failed: HTTP %s', getattr(resp, 'status_code', '?'))
        return None
    except Exception as exc:
        logger.warning('Webhook provider raised: %s', exc)
        return None


# ---------------------------------------------------------------------------
# Provider 6: Email OTP (free — SMTP or console)
# ---------------------------------------------------------------------------

def _send_email_otp(email: str, message: str) -> str | None:
    """
    Send OTP by email when an email address is available.

    Set MAIL_PROVIDER=smtp and configure MAIL_SMTP_* vars for real sending.
    Set MAIL_PROVIDER=console (default) to log to stdout (dev mode only).
    """
    if not email:
        return None

    provider_name = _env('MAIL_PROVIDER', 'console').lower()

    if provider_name == 'console':
        logger.warning(
            'EMAIL OTP (console fallback) → %s:\n%s', email, message)
        return 'email_console'

    if provider_name == 'smtp':
        host = _env('MAIL_SMTP_HOST')
        port = int(_env('MAIL_SMTP_PORT', '587'))
        user = _env('MAIL_SMTP_USER')
        passwd = _env('MAIL_SMTP_PASS')
        from_addr = _env('MAIL_FROM', user or 'noreply@glory2yah.net')

        if not (host and user and passwd):
            logger.warning('SMTP not configured — MAIL_SMTP_HOST/USER/PASS required')
            return None

        try:
            import smtplib
            from email.mime.text import MIMEText
            msg = MIMEText(message, 'plain', 'utf-8')
            msg['Subject'] = '🔐 Kòd verifikasyon Glory2YahPub'
            msg['From'] = from_addr
            msg['To'] = email
            with smtplib.SMTP(host, port, timeout=15) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.login(user, passwd)
                smtp.sendmail(from_addr, [email], msg.as_string())
            logger.info('OTP email sent to %s', email[:4] + '***')
            return 'email_smtp'
        except Exception as exc:
            logger.warning('SMTP email OTP failed: %s', exc)
            return None

    logger.warning('Unknown MAIL_PROVIDER=%r — skipping email OTP', provider_name)
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def send_otp(
    phone_e164: str,
    message: str,
    email: str | None = None,
) -> str | None:
    """
    Try every configured provider in order. Return the first provider name
    that delivers the OTP, or ``None`` when all providers fail or are unconfigured.

    Parameters
    ----------
    phone_e164:
        E.164 formatted phone number including leading '+', e.g. '+50942882076'.
    message:
        The human-readable OTP message text to send.
    email:
        Optional recipient email address (used only if all SMS/WA providers fail).

    Returns
    -------
    Provider name string on success, ``None`` on total failure.
    """
    # Strip leading '+' for providers that want digits-only
    phone_digits = phone_e164.lstrip('+')

    # 1. Textbee (free SMS via own Android — works for any international number)
    provider = _send_textbee(phone_e164, message)
    if provider:
        return provider

    # 2. CallMeBot WhatsApp (free but bound to one pre-registered number)
    provider = _send_callmebot(phone_digits, message)
    if provider:
        return provider

    # 3. UltraMsg (paid WhatsApp)
    provider = _send_ultramsg(phone_digits, message)
    if provider:
        return provider

    # 4. Meta WhatsApp Cloud API
    provider = _send_cloud_api(phone_digits, message)
    if provider:
        return provider

    # 5. Generic webhook
    provider = _send_webhook(phone_digits, message)
    if provider:
        return provider

    # 6. Email fallback
    if email:
        provider = _send_email_otp(email, message)
        if provider:
            return provider

    logger.warning(
        'OTP for %s NOT delivered — configure at least one of: '
        'TEXTBEE_API_KEY (free, recommended), CALLMEBOT_APIKEY, '
        'ULTRAMSG_*, WHATSAPP_CLOUD_*, WHATSAPP_ALERT_WEBHOOK_URL, '
        'or MAIL_PROVIDER=smtp + MAIL_SMTP_* for email fallback.',
        phone_e164[:6] + '***',
    )
    return None


def configured_providers() -> list[str]:
    """Return a list of provider names that are currently configured."""
    names = []
    if _env('TEXTBEE_API_KEY'):
        names.append('textbee')
    if _env('CALLMEBOT_APIKEY'):
        names.append('callmebot')
    if _env('ULTRAMSG_INSTANCE_ID') and _env('ULTRAMSG_TOKEN'):
        names.append('ultramsg')
    if _env('WHATSAPP_CLOUD_TOKEN') and _env('WHATSAPP_CLOUD_PHONE_ID'):
        names.append('whatsapp_cloud_api')
    if _env('WHATSAPP_ALERT_WEBHOOK_URL'):
        names.append('webhook')
    mail = _env('MAIL_PROVIDER', 'console')
    if mail == 'smtp' and _env('MAIL_SMTP_HOST') and _env('MAIL_SMTP_USER'):
        names.append('email_smtp')
    elif mail == 'console':
        names.append('email_console')
    return names
