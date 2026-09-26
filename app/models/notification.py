"""
Notification Models
===================
Central notification store + PWA Web Push subscriptions + user preferences.

Design goals (see GLORY2YAHPUB notification spec):
  * Flexible: `type` + `category` + `data_json` mean NEW notification kinds
    never require a schema change (only a template registration).
  * Multi-device: a user may own many active PushSubscription rows.
  * No duplicate endpoints: `endpoint` is UNIQUE and reused on re-subscribe.
  * Never destructive: financial/admin kinds are exempt from auto-cleanup.

FIX AND EXTEND: this module is additive — no existing model was modified.
"""
from datetime import datetime

from app import db
from app.models.base import BaseModel


# ─────────────────────────── priorities & categories ───────────────────────────
PRIORITY_LOW = 'low'
PRIORITY_NORMAL = 'normal'
PRIORITY_HIGH = 'high'
PRIORITY_URGENT = 'urgent'


class Notification(BaseModel):
    """One notification addressed to one user (database = source of truth)."""

    __tablename__ = 'notifications'

    recipient_id = db.Column(
        db.Integer, db.ForeignKey('users.id'), nullable=False, index=True
    )
    # Denormalised helper (users.whatsapp is the app-wide business key) — lets
    # modules that only know a whatsapp number notify without an extra lookup.
    recipient_whatsapp = db.Column(db.String(20), index=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    actor_name = db.Column(db.String(100))

    # "post_like", "order_created", "gkach_credit", "ad_approved", ...
    type = db.Column(db.String(50), nullable=False, index=True)
    # "likes", "comments", "messages", "orders", "gkach", "ads", "events",
    # "match", "system", "security", "admin"
    category = db.Column(db.String(30), nullable=False, default='system', index=True)
    priority = db.Column(db.String(10), nullable=False, default=PRIORITY_NORMAL, index=True)

    # Rendered content (stored in the language of the recipient at create time —
    # `type` + `data_json` allow re-rendering in another language later).
    title = db.Column(db.String(160))
    message = db.Column(db.Text, nullable=False)

    icon = db.Column(db.String(16))
    image = db.Column(db.String(500))

    # Clickable destination: /post/123, /gkach/transaction/789 ...
    entity_type = db.Column(db.String(40), index=True)
    entity_id = db.Column(db.String(64), index=True)
    url = db.Column(db.String(500))

    # Free-form context ({'amount': 100, 'reference': '...'}) enable i18n
    # re-render + grouped summaries without new columns.
    data_json = db.Column(db.Text)

    # Anti-spam grouping: consecutive like/comment on the SAME entity within the
    # aggregation window increment this counter instead of creating N rows.
    aggregate_count = db.Column(db.Integer, nullable=False, default=1)

    is_read = db.Column(db.Boolean, nullable=False, default=False, index=True)
    read_at = db.Column(db.DateTime)

    pushed_at = db.Column(db.DateTime)

    __table_args__ = (
        db.Index('ix_notifications_recipient_read_created',
                 'recipient_id', 'is_read', 'created_at'),
        db.Index('ix_notifications_recipient_type_entity',
                 'recipient_id', 'type', 'entity_type', 'entity_id'),
    )

    # ── helpers ───────────────────────────────────────────────────────────────
    def mark_read(self):
        """Flag as read (idempotent)."""
        if not self.is_read:
            self.is_read = True
            self.read_at = datetime.utcnow()

    def get_data(self):
        """Decode data_json safely (never raises)."""
        import json
        if not self.data_json:
            return {}
        try:
            return json.loads(self.data_json) or {}
        except Exception:
            return {}

    def to_dict(self):
        """Serialise for the REST API / WebSocket payload."""
        return {
            'id': self.id,
            'recipient_id': self.recipient_id,
            'sender_id': self.sender_id,
            'actor_name': self.actor_name,
            'type': self.type,
            'category': self.category,
            'priority': self.priority,
            'title': self.title,
            'message': self.message,
            'icon': self.icon,
            'image': self.image,
            'entity_type': self.entity_type,
            'entity_id': self.entity_id,
            'url': self.url,
            'data': self.get_data(),
            'aggregate_count': self.aggregate_count or 1,
            'is_read': bool(self.is_read),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'read_at': self.read_at.isoformat() if self.read_at else None,
        }

    def __repr__(self):
        return f'<Notification {self.id} {self.type} -> user {self.recipient_id}>'


class PushSubscription(BaseModel):
    """One browser/device Web Push subscription (a user may have several)."""

    __tablename__ = 'push_subscriptions'

    user_id = db.Column(
        db.Integer, db.ForeignKey('users.id'), nullable=False, index=True
    )
    endpoint = db.Column(db.String(500), nullable=False, unique=True, index=True)
    p256dh = db.Column(db.String(255), nullable=False)
    auth = db.Column(db.String(255), nullable=False)

    device_type = db.Column(db.String(30))   # mobile / tablet / desktop
    browser = db.Column(db.String(40))
    os = db.Column(db.String(40))
    user_agent = db.Column(db.String(400))

    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    fail_count = db.Column(db.Integer, nullable=False, default=0)
    last_used_at = db.Column(db.DateTime)

    def deactivate(self, reason=''):
        """Mark endpoint dead (410/404 from the push service)."""
        self.is_active = False
        if reason:
            import logging
            logging.getLogger(__name__).info(
                'PushSubscription #%s deactivated: %s', self.id, reason
            )

    def to_dict(self):
        return {
            'id': self.id,
            'device_type': self.device_type,
            'browser': self.browser,
            'os': self.os,
            'is_active': bool(self.is_active),
            'last_used_at': self.last_used_at.isoformat() if self.last_used_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f'<PushSubscription {self.id} user={self.user_id} active={self.is_active}>'


class NotificationPreference(BaseModel):
    """Per-user notification preferences (categories are JSON → extensible)."""

    __tablename__ = 'notification_preferences'

    user_id = db.Column(
        db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True, index=True
    )
    language = db.Column(db.String(5), default='ht')       # ht / fr / en
    push_enabled = db.Column(db.Boolean, nullable=False, default=True)
    realtime_enabled = db.Column(db.Boolean, nullable=False, default=True)
    sound_enabled = db.Column(db.Boolean, nullable=False, default=False)

    # {category: bool} — missing keys fall back to the service defaults.
    categories_json = db.Column(db.Text)

    def get_categories(self):
        import json
        if not self.categories_json:
            return {}
        try:
            data = json.loads(self.categories_json)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def set_categories(self, mapping):
        import json
        self.categories_json = json.dumps(mapping or {})

    def to_dict(self):
        return {
            'language': self.language or 'ht',
            'push_enabled': bool(self.push_enabled),
            'realtime_enabled': bool(self.realtime_enabled),
            'sound_enabled': bool(self.sound_enabled),
            'categories': self.get_categories(),
        }

    def __repr__(self):
        return f'<NotificationPreference user={self.user_id}>'
