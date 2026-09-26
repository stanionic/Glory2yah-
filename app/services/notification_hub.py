"""
Notification Hub — central notification service
==============================================
Single entry point used by every module (posts, marketplace, Gkach, ads,
messaging, MATCH, admin, …). Pipeline (spec §13/§34):

    event → NotificationHub.create() → Database (source of truth)
                                     → Socket.IO room "user_<id>" (real-time)
                                     → Web Push (background / app closed)

Hard rules
----------
* **Never breaks the caller.** Every public method swallows and logs its own
  errors — a failed notification must never fail the business action (§35).
* **No duplicate systems.** Re-uses the app's existing Socket.IO instance
  (`app.socketio`) whose `message_queue` is already Redis, so real-time events
  fan out across gunicorn workers without adding anything new.
* **Preferences & mute respected server-side** (§20/§21) — except security
  kinds, which are always delivered.
* **Anti-spam aggregation** (§41/§42): repeated likes/comments on the SAME
  entity within a short window bump `aggregate_count` instead of creating N
  rows. Orders/Gkach/security are never grouped.

The existing `app/services/notification_service.py` (WhatsApp helpers) is kept
untouched — this module only adds the in-app/push layer.
"""
import logging
from datetime import datetime, timedelta

from flask import current_app

from app.services import notification_templates as T

logger = logging.getLogger(__name__)

# Notification types that may be merged into one grouped row.
AGGREGATABLE_TYPES = {
    'post_like', 'post_comment', 'post_share', 'new_follower',
    'message_new', 'post_saved',
}

DEFAULT_AGGREGATE_WINDOW_SECONDS = 3600
MAX_PUSH_AGGREGATE_WINDOW_SECONDS = 300

# Preferences always honoured, whatever the user muted.
NEVER_MUTABLE_CATEGORIES = ('security',)


class NotificationHub:
    """Central notification service (all methods are class-level / stateless)."""

    # ═══════════════════════════ preferences ═══════════════════════════
    @classmethod
    def get_or_create_preferences(cls, user_id):
        """Return the user's NotificationPreference row (created on demand)."""
        from app import db
        from app.models.notification import NotificationPreference

        pref = NotificationPreference.query.filter_by(user_id=user_id).first()
        if pref:
            return pref
        pref = NotificationPreference(user_id=user_id)
        pref.set_categories({})
        db.session.add(pref)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
        return pref

    @classmethod
    def category_allowed(cls, user_id, category):
        """Respect the user's mute switches (§21). Defaults to allowed."""
        if not category or category in NEVER_MUTABLE_CATEGORIES:
            return True
        try:
            pref = cls.get_or_create_preferences(user_id)
            cats = dict(T.default_categories())
            cats.update({k: bool(v) for k, v in (pref.get_categories() or {}).items()})
            return bool(cats.get(category, True))
        except Exception:
            return True

    @classmethod
    def _language_for(cls, user_id):
        """Recipient language for template rendering (ht / fr / en)."""
        try:
            pref = cls.get_or_create_preferences(user_id)
            lang = (pref.language or T.DEFAULT_LANG).lower()[:2]
            return lang if lang in T.SUPPORTED_LANGS else T.DEFAULT_LANG
        except Exception:
            return T.DEFAULT_LANG

    @classmethod
    def _realtime_enabled(cls, user_id):
        try:
            return bool(cls.get_or_create_preferences(user_id).realtime_enabled)
        except Exception:
            return True

    @classmethod
    def _push_enabled(cls, user_id):
        try:
            return bool(cls.get_or_create_preferences(user_id).push_enabled)
        except Exception:
            return True

    # ═══════════════════════════ core: create ═══════════════════════════
    @classmethod
    def create(cls, recipient_id=None, notification_type='system',
               context=None, sender_id=None, actor_name=None,
               recipient_whatsapp=None, title=None, message=None,
               icon=None, image=None, url=None, category=None, priority=None,
               entity_type=None, entity_id=None, data=None,
               aggregate=True, push=True, realtime=True, force=False,
               commit=True):
        """Create (+ persist, emit, push) one notification.

        Returns the `Notification` instance, or None when the notification was
        intentionally skipped (muted category / same actor / no recipient) —
        never raises.

        `force=True` bypasses mute preferences (security / critical alerts).
        """
        from app import db
        from app.models.notification import Notification

        try:
            recip = cls._resolve_recipient(recipient_id, recipient_whatsapp)
            if not recip:
                return None
            recipient_id = recip.id

            if sender_id and int(sender_id) == int(recipient_id):
                return None  # never notify yourself

            lang = cls._language_for(recipient_id)
            ctx = dict(context or {})
            if data:
                ctx.update(data)
            ctx.setdefault('actor', actor_name or ctx.get('actor') or 'Glory2YahPub')
            ctx.setdefault('recipient', recip.pseudo or '')

            rendered = T.render(notification_type, ctx, lang=lang,
                                title=title, message=message, icon=icon)
            cat = (category or rendered.get('category') or
                   T.resolve_category(notification_type)).lower()
            prio = (priority or rendered.get('priority') or
                    T.resolve_priority(notification_type)).lower()
            final_url = url or rendered.get('url') or None
            final_icon = icon or rendered.get('icon') or '🔔'
            final_message = rendered.get('message') or (message or '')
            final_title = (title or rendered.get('title') or '')[:160]

            if not final_message:
                final_message = final_title or 'Glory2YahPub'

            # ── mute / preference gate (§21) ──
            if not force and not cls.category_allowed(recipient_id, cat):
                logger.debug('Notification skipped (muted) user=%s category=%s',
                             recipient_id, cat)
                return None

            # ── anti-spam aggregation (§41/§42) ──
            notif = None
            if aggregate and notification_type in AGGREGATABLE_TYPES and entity_id:
                notif = cls._find_aggregate_target(recipient_id, notification_type, entity_id)
                if notif is not None:
                    notif.aggregate_count = (notif.aggregate_count or 1) + 1
                    notif.actor_name = ctx.get('actor') or notif.actor_name
                    notif.is_read = False
                    notif.read_at = None
                    cls._refresh_aggregated_text(notif, notification_type, ctx, lang)
                    db.session.add(notif)
                    if commit:
                        db.session.commit()
                    cls._dispatch(notif, push=push, realtime=realtime,
                                  grouped=True, lang=lang)
                    return notif

            notif = Notification(
                recipient_id=recipient_id,
                recipient_whatsapp=recip.whatsapp,
                sender_id=sender_id,
                actor_name=actor_name or ctx.get('actor'),
                type=notification_type,
                category=cat,
                priority=prio,
                title=final_title,
                message=final_message,
                icon=final_icon,
                image=image,
                entity_type=entity_type,
                entity_id=str(entity_id) if entity_id else None,
                url=final_url,
                data_json=cls._dump(ctx),
                aggregate_count=1,
                is_read=False,
            )
            db.session.add(notif)
            if commit:
                db.session.commit()
            logger.info('Notification created id=%s type=%s user=%s',
                        notif.id, notification_type, recipient_id)
            cls._dispatch(notif, push=push, realtime=realtime, lang=lang)
            return notif

        except Exception as exc:  # notification failure must NEVER break the action
            logger.warning('NotificationHub.create failed (type=%s): %s',
                           notification_type, exc)
            try:
                db.session.rollback()
            except Exception:
                pass
            return None

    # Backwards/§18-friendly alias
    create_notification = create

    # ═══════════════════════════ internals ═══════════════════════════
    @staticmethod
    def _resolve_recipient(recipient_id=None, recipient_whatsapp=None):
        """Look up the recipient User row by id or whatsapp (never raises)."""
        from app.models.user import User
        try:
            if recipient_id:
                return User.query.get(recipient_id)
            if recipient_whatsapp:
                return User.query.filter_by(whatsapp=recipient_whatsapp).first()
        except Exception as exc:
            logger.debug('Recipient lookup failed: %s', exc)
        return None

    @staticmethod
    def _dump(ctx):
        try:
            import json
            safe = {k: v for k, v in (ctx or {}).items()
                    if isinstance(v, (str, int, float, bool, list, dict, type(None)))}
            return json.dumps(safe, ensure_ascii=False)[:4000]
        except Exception:
            return None

    @classmethod
    def _aggregate_window(cls):
        try:
            return int(current_app.config.get('NOTIFICATIONS_AGGREGATE_WINDOW',
                                              DEFAULT_AGGREGATE_WINDOW_SECONDS))
        except Exception:
            return DEFAULT_AGGREGATE_WINDOW_SECONDS

    @classmethod
    def _find_aggregate_target(cls, recipient_id, notification_type, entity_id):
        """Last un-aggregated row of the same kind/entity inside the window."""
        from app.models.notification import Notification
        try:
            since = datetime.utcnow() - timedelta(seconds=cls._aggregate_window())
            return (Notification.query
                    .filter(Notification.recipient_id == recipient_id,
                            Notification.type == notification_type,
                            Notification.entity_id == str(entity_id),
                            Notification.created_at >= since)
                    .order_by(Notification.created_at.desc())
                    .first())
        except Exception:
            return None

    @classmethod
    def _refresh_aggregated_text(cls, notif, notification_type, ctx, lang):
        """Re-render a grouped row: \"Marie, Jean et 8 autres…\"."""
        try:
            extra = {'count': notif.aggregate_count}
            merged = dict(ctx)
            merged.update(extra)
            rendered = T.render(notification_type, merged, lang=lang,
                                count=notif.aggregate_count)
            if rendered.get('message'):
                notif.message = rendered['message']
            if rendered.get('title'):
                notif.title = rendered['title'][:160]
            notif.data_json = cls._dump(merged)
        except Exception as exc:
            logger.debug('Aggregate re-render failed: %s', exc)

    @classmethod
    def _dispatch(cls, notif, push=True, realtime=True, grouped=False, lang=None):
        """Fan a persisted notification out to Socket.IO (+ Web Push async)."""
        payload = notif.to_dict()
        payload['grouped'] = bool(grouped)
        payload['lang'] = lang or T.DEFAULT_LANG
        payload['unread_count'] = cls.get_unread_count(notif.recipient_id)
        if realtime and cls._realtime_enabled(notif.recipient_id):
            cls.send_realtime(notif.recipient_id, payload)
        if push and cls._push_enabled(notif.recipient_id):
            cls.send_push(notif.recipient_id, payload)

    # ═══════════════════════════ transport ═══════════════════════════
    @classmethod
    def send_realtime(cls, user_id, payload):
        """Emit to the user's private Socket.IO room (cross-worker via Redis)."""
        try:
            from app import socketio
            room = f'user_{user_id}'
            socketio.emit('notification', payload, room=room, namespace='/')
            socketio.emit('notifications:unread', {
                'unread_count': payload.get('unread_count', cls.get_unread_count(user_id))
            }, room=room, namespace='/')
            logger.debug('Realtime notification emitted to %s', room)
            return True
        except Exception as exc:
            logger.warning('Realtime emit failed for user=%s: %s', user_id, exc)
            return False

    @classmethod
    def send_push(cls, user_id, payload):
        """Queue a Web Push to all the user's active devices (non-blocking)."""
        try:
            from app.services.push_service import PushService
            if not PushService.is_configured():
                return 0
            app = current_app._get_current_object()
            push_payload = {
                'id': payload.get('id'),
                'title': payload.get('title') or 'Glory2YahPub',
                'body': payload.get('message') or '',
                'icon': payload.get('icon') or '🔔',
                'image': payload.get('image'),
                'url': payload.get('url') or '/',
                'category': payload.get('category'),
                'priority': payload.get('priority'),
                'tag': cls._push_tag(payload),
            }
            PushService.send_async(app, user_id, push_payload)
            return 1
        except Exception as exc:
            logger.warning('Push dispatch failed for user=%s: %s', user_id, exc)
            return 0

    @staticmethod
    def _push_tag(payload):
        """Notification tag → browsers replace/group same-tag pushes (§41)."""
        cat = payload.get('category') or 'system'
        if cat in T.PROTECTED_CATEGORIES:
            return f"g2y-{cat}-{payload.get('id') or ''}"
        return f"g2y-{cat}-{payload.get('entity_type') or ''}-{payload.get('entity_id') or ''}"

    # ═══════════════════════ read / sync API (§18/§30) ═══════════════════════
    @classmethod
    def get_unread_count(cls, user_id):
        """Badge number — real count of unread rows (never raises → 0)."""
        from app.models.notification import Notification
        try:
            return int(Notification.query.filter_by(
                recipient_id=user_id, is_read=False).count())
        except Exception:
            return 0

    @classmethod
    def get_notifications(cls, user_id, page=1, per_page=20, unread_only=False,
                          category=None):
        """Paginated list (spec §24 — never load everything at once).

        Returns dict(items, page, per_page, total, pages, has_more, unread_count).
        """
        from app.models.notification import Notification
        try:
            page = max(1, int(page or 1))
            per_page = min(max(1, int(per_page or 20)), 50)
            q = Notification.query.filter_by(recipient_id=user_id)
            if unread_only:
                q = q.filter_by(is_read=False)
            if category:
                q = q.filter_by(category=category)
            pagination = (q.order_by(Notification.created_at.desc(),
                                     Notification.id.desc())
                          .paginate(page=page, per_page=per_page, error_out=False))
            lang = cls._language_for(user_id)
            _now = datetime.utcnow()
            items = []
            for n in pagination.items:
                item = n.to_dict()
                # Relative label ("2 min") rendered server-side so the mobile
                # sheet shows it immediately; the JS also refreshes it live.
                item['time_ago'] = T.humanize_delta(n.created_at, lang, now=_now)
                item['category_label'] = cls.category_label(n.category, lang)
                items.append(item)
            return {
                'items': items,
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages,
                'has_more': pagination.has_next,
                'unread_count': cls.get_unread_count(user_id),
            }
        except Exception as exc:
            logger.warning('get_notifications failed user=%s: %s', user_id, exc)
            return {'items': [], 'page': 1, 'per_page': 20, 'total': 0,
                    'pages': 0, 'has_more': False, 'unread_count': 0}

    @classmethod
    def mark_as_read(cls, notification_id, user_id):
        """Ownership-checked single mark-as-read (§27)."""
        from app import db
        from app.models.notification import Notification
        try:
            notif = Notification.query.filter_by(
                id=notification_id, recipient_id=user_id).first()
            if not notif:
                return False
            if not notif.is_read:
                notif.mark_read()
                db.session.commit()
                logger.info('Notification marked read id=%s user=%s',
                            notification_id, user_id)
                cls._emit_unread(user_id)
            return True
        except Exception as exc:
            logger.warning('mark_as_read failed: %s', exc)
            try:
                db.session.rollback()
            except Exception:
                pass
            return False

    @classmethod
    def mark_all_as_read(cls, user_id, category=None):
        """Bulk mark-as-read; returns how many rows were updated."""
        from app import db
        from app.models.notification import Notification
        try:
            q = Notification.query.filter_by(recipient_id=user_id, is_read=False)
            if category:
                q = q.filter_by(category=category)
            rows = q.all()
            now = datetime.utcnow()
            for n in rows:
                n.is_read = True
                n.read_at = now
            db.session.commit()
            if rows:
                logger.info('%s notifications marked read for user=%s',
                            len(rows), user_id)
                cls._emit_unread(user_id)
            return len(rows)
        except Exception as exc:
            logger.warning('mark_all_as_read failed: %s', exc)
            try:
                db.session.rollback()
            except Exception:
                pass
            return 0

    @classmethod
    def delete_notification(cls, notification_id, user_id):
        """Ownership-checked delete (soft delete via BaseModel if available)."""
        from app import db
        from app.models.notification import Notification
        try:
            notif = Notification.query.filter_by(
                id=notification_id, recipient_id=user_id).first()
            if not notif:
                return False
            # Soft-delete when the model supports it, hard delete otherwise.
            if hasattr(notif, 'soft_delete'):
                notif.soft_delete()
            else:
                db.session.delete(notif)
            db.session.commit()
            cls._emit_unread(user_id)
            return True
        except Exception as exc:
            logger.warning('delete_notification failed: %s', exc)
            try:
                db.session.rollback()
            except Exception:
                pass
            return False

    @classmethod
    def _emit_unread(cls, user_id):
        try:
            from app import socketio
            socketio.emit('notifications:unread',
                          {'unread_count': cls.get_unread_count(user_id)},
                          room=f'user_{user_id}', namespace='/')
        except Exception:
            pass

    # ═══════════════════════ category / i18n labels ═══════════════════════
    @classmethod
    def category_label(cls, category, lang=None):
        """Human-readable category label in `lang` (falls back to DEFAULT_LANG)."""
        try:
            from app.services.notification_templates import CATEGORY_LABELS, DEFAULT_LANG
            if lang is None:
                lang = DEFAULT_LANG
            key = (category or '').lower() if category else ''
            table = CATEGORY_LABELS.get(key) or {}
            label = table.get(lang) or table.get(DEFAULT_LANG) or (category or 'Systèm')
            return str(label)
        except Exception:
            return str(category or 'Systèm')
