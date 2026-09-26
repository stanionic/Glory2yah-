"""
Web Push Service (PWA background notifications)
===============================================
Sends VAPID-signed Web Push messages to the endpoints stored in
`PushSubscription`. Application notifications never depend on this module:

  * `pywebpush` is imported LAZILY and guarded. If the package (or the VAPID
    keys) is missing, `PushService.is_configured()` returns False, every send
    becomes a logged no-op and the rest of the app keeps working.
  * Sending runs in a short-lived daemon thread (`send_async`) so the HTTP
    request that triggered the notification is never blocked — required because
    production runs gunicorn `sync` workers (no async worker class).
  * Dead endpoints (404/410 from the push service) are deactivated instead of
    being retried forever (spec §25).

Config (env vars):
    VAPID_PUBLIC_KEY   — applicationServerKey given to the browser
    VAPID_PRIVATE_KEY  — PEM/DER base64 private key used to sign
    VAPID_SUBJECT      — mailto:you@example.com (or an https URL)
"""
import json
import logging
import os
import threading

from flask import current_app

logger = logging.getLogger(__name__)

# Statuses meaning "this endpoint no longer exists" → deactivate it.
_DEAD_ENDPOINT_STATUSES = (404, 410)


class PushService:
    """Web Push transport (thin, safe, no hard dependency on pywebpush)."""

    # ────────────────────────── configuration ──────────────────────────
    @staticmethod
    def _cfg(key, default=None):
        try:
            return current_app.config.get(key, default)
        except Exception:
            return os.environ.get(key, default)

    @classmethod
    def public_key(cls):
        return cls._cfg('VAPID_PUBLIC_KEY', '')

    @classmethod
    def private_key(cls):
        return cls._cfg('VAPID_PRIVATE_KEY', '')

    @classmethod
    def subject(cls):
        return cls._cfg('VAPID_SUBJECT', 'mailto:admin@glory2yahpub.com')

    @classmethod
    def is_configured(cls):
        """True only when pywebpush AND both VAPID keys are available."""
        if not (cls.public_key() and cls.private_key()):
            return False
        try:
            import pywebpush  # noqa: F401
            return True
        except Exception:
            return False

    # ────────────────────────── sending ──────────────────────────
    @classmethod
    def send_to_subscription(cls, subscription, payload, ttl=86400, urgency='normal'):
        """Send one push message.

        Returns True on success. Returns False on failure; deactivates the
        subscription when the push service reports it as gone (404/410).
        """
        try:
            from pywebpush import webpush, WebPushException
        except Exception as exc:  # pywebpush not installed → soft no-op
            logger.info('Web Push skipped (pywebpush unavailable): %s', exc)
            return False

        if not cls.is_configured():
            logger.debug('Web Push skipped: VAPID keys not configured')
            return False

        info = {
            'endpoint': subscription.endpoint,
            'keys': {'p256dh': subscription.p256dh, 'auth': subscription.auth},
        }
        try:
            webpush(
                subscription_info=info,
                data=json.dumps(payload),
                vapid_private_key=cls.private_key(),
                vapid_claims={'sub': cls.subject()},
                ttl=ttl,
                headers={'Urgency': urgency},
            )
            return True
        except WebPushException as exc:
            status = getattr(getattr(exc, 'response', None), 'status_code', None)
            if status in _DEAD_ENDPOINT_STATUSES:
                logger.info('Push endpoint expired (HTTP %s) — deactivating', status)
                subscription.deactivate(f'HTTP {status}')
                cls._safe_commit()
            else:
                subscription.fail_count = (subscription.fail_count or 0) + 1
                logger.warning('Web Push failed (HTTP %s): %s', status, exc)
            return False
        except Exception as exc:
            subscription.fail_count = (subscription.fail_count or 0) + 1
            logger.warning('Web Push error: %s', exc)
            return False

    @classmethod
    def send_to_user(cls, user_id, payload):
        """Send `payload` to every ACTIVE device of `user_id`.

        Returns the number of successfully delivered devices.
        """
        from app import db
        from app.models.notification import PushSubscription

        if not cls.is_configured():
            return 0

        sent = 0
        try:
            subs = PushSubscription.query.filter_by(user_id=user_id, is_active=True).all()
        except Exception as exc:
            logger.warning('PushSubscription lookup failed: %s', exc)
            return 0

        from datetime import datetime
        for sub in subs:
            if cls.send_to_subscription(sub, payload):
                sub.last_used_at = datetime.utcnow()
                sent += 1
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
        return sent

    # ────────────────────────── async wrapper ──────────────────────────
    @classmethod
    def send_async(cls, app, user_id, payload):
        """Fire-and-forget push in a daemon thread (never blocks the request).

        `app` must be the real Flask app object so a fresh app context can be
        pushed inside the thread.
        """
        try:
            if app and app.config.get('NOTIFICATIONS_PUSH_INLINE') is False:
                return None
        except Exception:
            pass

        def _worker():
            try:
                with app.app_context():
                    cls.send_to_user(user_id, payload)
            except Exception as exc:
                # A notification error must NEVER surface to the main action.
                logger.warning('Async push worker failed for user=%s: %s', user_id, exc)

        t = threading.Thread(target=_worker, name=f'g2y-push-{user_id}', daemon=True)
        t.start()
        return t

    @staticmethod
    def _safe_commit():
        try:
            from app import db
            db.session.commit()
        except Exception:
            try:
                from app import db as _db
                _db.session.rollback()
            except Exception:
                pass
