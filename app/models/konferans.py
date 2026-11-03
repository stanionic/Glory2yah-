from app.models.base import BaseModel
from app import db
from datetime import datetime

class KonferansRoom(BaseModel):
    __tablename__ = 'konferans_rooms'
    
    room_id = db.Column(db.String(128), unique=True, nullable=False)
    room_code = db.Column(db.String(10), unique=True, nullable=False)
    room_name = db.Column(db.String(255), nullable=False)
    creator_name = db.Column(db.String(255), nullable=False)
    password = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    creator_whatsapp = db.Column(db.String(30), nullable=True)
    
    # E-learning / session metadata (added via bootstrap migration)
    room_type = db.Column(db.String(16), default='classic')
    class_id = db.Column(db.Integer, nullable=True)
    lesson_id = db.Column(db.Integer, nullable=True)
    scheduled_at = db.Column(db.DateTime, nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    ended_at = db.Column(db.DateTime, nullable=True)
    max_participants = db.Column(db.Integer, default=50)
    mic_locked = db.Column(db.Boolean, default=False)
    cam_locked = db.Column(db.Boolean, default=False)
    chat_locked = db.Column(db.Boolean, default=False)
    class_locked = db.Column(db.Boolean, default=False)
    whiteboard_id = db.Column(db.Integer, nullable=True)
    
    # Gkach billing persistence
    # NOTE: gkach_per_hour / credit_bought_minutes are LEGACY pay-as-you-go
    # fields (250 Gkach/lè). The room now runs on the monthly KONFERANS
    # subscription (KonferansSubscription, 500 Gkach/mwa). Columns stay for
    # rows billed under the old model; nothing charges against them anymore.
    gkach_charged_total = db.Column(db.Integer, default=0)
    credit_bought_minutes = db.Column(db.Integer, default=0)
    gkach_per_hour = db.Column(db.Integer, default=250)
    free_minutes = db.Column(db.Integer, default=45)

    # Participant download permission. Default False = owner must opt in
    # (per-request approval is still required on top of this toggle).
    # New column: fresh DBs get it via db.create_all(); existing DBs need the
    # idempotent `_migrate_konferans_subscription.py`. Code guards with
    # getattr so a missing column never breaks the app.
    allow_download = db.Column(db.Boolean, default=False)
    
    # Relationship
    user = db.relationship('User', backref='konferans_rooms', lazy=True)


class KonferansRecording(BaseModel):
    __tablename__ = 'konferans_recordings'
    
    room_id = db.Column(db.String(128), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    # Nullable for device-source recordings (the media bytes live on the room
    # owner's device, never on the server). Legacy server-uploaded files keep
    # a real path here. Rows written on an OLD database that still has a
    # NOT NULL constraint get a 'device://' sentinel instead of NULL.
    file_path = db.Column(db.String(500), nullable=True)
    file_size = db.Column(db.Integer, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True, index=True)

    # True when the master copy is held on the owner's device (memory +
    # IndexedDB/OPFS). Participants must go through the owner-approval
    # download flow; there is no server file to fetch.
    stored_on_owner_device = db.Column(db.Boolean, default=False)
    owner_user_id = db.Column(db.Integer, nullable=True, index=True)
    # Best-effort count of rooms/participants at save time, for the owner's
    # "Ki moun ki ka mande download" panel. Purely informational.
    participant_count_hint = db.Column(db.Integer, nullable=True)

    # Optional human title (used by WhatsApp audio-save / title-frame features)
    # New column: safe on fresh DBs via db.create_all(); existing DBs need the
    # idempotent migration script `_migrate_konferans_stream.py` (code always
    # guards with getattr, so a missing column never breaks the app).
    title = db.Column(db.String(255), nullable=True)

    def to_dict(self):
        data = super().to_dict()
        try:
            # Device-source recordings have no server URL: exposing one would
            # advertise a route that can only ever 404 for them.
            if not getattr(self, 'stored_on_owner_device', False):
                data['url'] = f"/konferans/download_recording/{self.filename}"
            else:
                data['url'] = None
                data['device_source'] = True
        except Exception:
            pass
        return data


class KonferansStreamSession(BaseModel):
    """A live-stream session of a Konferans room to an external platform.

    Owner-initiated. The raw stream key is NEVER stored — only a masked
    version for display. Platforms: facebook, youtube, tiktok, whatsapp,
    custom (any RTMP(S) ingest).
    """
    __tablename__ = 'konferans_stream_sessions'

    room_id = db.Column(db.String(128), nullable=False, index=True)
    platform = db.Column(db.String(32), nullable=False, default='custom', index=True)
    title = db.Column(db.String(255), nullable=True)
    ingest_url = db.Column(db.String(500), nullable=True)
    stream_key_masked = db.Column(db.String(255), nullable=True)  # masked only
    status = db.Column(db.String(16), nullable=False, default='live', index=True)  # live|stopped|error
    started_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    stopped_at = db.Column(db.DateTime, nullable=True)
    duration_seconds = db.Column(db.Integer, nullable=True)
    started_by = db.Column(db.String(255), nullable=True)
    # Set when the broadcast was created through the Facebook Graph API, so the
    # live can be ended server-side. New column: created for fresh DBs by
    # db.create_all(); existing DBs get it from the idempotent bootstrap
    # migration in app/__init__.py (code always guards with getattr).
    platform_live_id = db.Column(db.String(64), nullable=True)

    def to_dict(self):
        data = super().to_dict()
        try:
            data['started_at'] = self.started_at.isoformat() if self.started_at else None
            data['stopped_at'] = self.stopped_at.isoformat() if self.stopped_at else None
        except Exception:
            pass
        return data


class KonferansPlatformConnection(BaseModel):
    """A connected external platform account for KONFERANS auto-Live.

    Currently used for Facebook: the owner links a Page once (OAuth) and we keep
    the long-lived Page access token so KONFERANS can create the broadcast and
    read back the ingest URL + stream key on each start.

    The token is stored ENCRYPTED (see konferans/facebook_live.py); the raw
    stream key is never stored at all.
    """
    __tablename__ = 'konferans_platform_connections'

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    platform = db.Column(db.String(32), nullable=False, default='facebook', index=True)
    account_id = db.Column(db.String(64), nullable=True)      # e.g. Facebook Page ID
    account_name = db.Column(db.String(255), nullable=True)   # e.g. Page name
    token_enc = db.Column(db.Text, nullable=True)             # encrypted access token
    scopes = db.Column(db.String(512), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    def __repr__(self):
        return f'<KonferansPlatformConnection {self.platform}:{self.account_name}>'


class KonferansSubscription(BaseModel):
    """Monthly KONFERANS subscription of a room owner (one row per user).

    Replaces the old pay-as-you-go 250 Gkach/lè model: after the room's free
    45 minutes the owner needs an ACTIVE (or TRIAL) subscription here, which
    buys UNLIMITED conference time for the whole month across all their rooms.

    Mirrors the Jere Biznis subscription rules: a free trial window, a
    500 Gkach/month price, multi-month prepayment (1/3/6/12/custom) whose
    extension STACKS on the current expiration, and rooms/data are never
    deleted when a subscription lapses.
    """
    __tablename__ = 'konferans_subscriptions'

    STATUS_TRIAL = 'TRIAL'
    STATUS_ACTIVE = 'ACTIVE'
    STATUS_EXPIRED = 'EXPIRED'

    # The subscription is per USER (the owner), not per room — one room can
    # have many rooms, all covered by the same plan.
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True, index=True)
    status = db.Column(db.String(30), nullable=False, default=STATUS_TRIAL)
    monthly_price_gkach = db.Column(db.Integer, nullable=False, default=500)
    trial_start = db.Column(db.DateTime, nullable=True)
    trial_end = db.Column(db.DateTime, nullable=True)
    subscription_start = db.Column(db.DateTime, nullable=True)
    expiration = db.Column(db.DateTime, nullable=True, index=True)
    last_verified_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship('User', backref='konferans_subscription', lazy=True)

    def compute_status(self, now=None):
        """ACTIVE (paid) takes priority over TRIAL: a paying owner is active."""
        now = now or datetime.utcnow()
        if self.expiration is not None and now < self.expiration:
            return self.STATUS_ACTIVE
        if self.trial_end is not None and now < self.trial_end:
            return self.STATUS_TRIAL
        return self.STATUS_EXPIRED

    def is_entitled(self, now=None):
        """True while the owner may keep a room running past the free window."""
        return self.compute_status(now) in (self.STATUS_ACTIVE, self.STATUS_TRIAL)

    def days_remaining(self, now=None):
        now = now or datetime.utcnow()
        status = self.compute_status(now)
        if status == self.STATUS_ACTIVE:
            return max(0, (self.expiration - now).days)
        if status == self.STATUS_TRIAL and self.trial_end:
            return max(0, (self.trial_end - now).days)
        return 0

    def to_dict(self):
        data = super().to_dict()
        now = datetime.utcnow()
        try:
            data['status'] = self.compute_status(now)
            data['entitled'] = data['status'] in (self.STATUS_ACTIVE, self.STATUS_TRIAL)
            data['days_remaining'] = self.days_remaining(now)
            data['expiration'] = self.expiration.isoformat() if self.expiration else None
            data['trial_end'] = self.trial_end.isoformat() if self.trial_end else None
            data['created_at'] = self.created_at.isoformat() if self.created_at else None
        except Exception:
            pass
        return data


class KonferansPayment(BaseModel):
    """Idempotent Gkach payment record for a KONFERANS subscription.

    idempotency_key is UNIQUE so a double-clicked "Peye" button (or a retried
    request after a timeout) can never charge the owner twice.
    """
    __tablename__ = 'konferans_payments'

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    transaction_id = db.Column(db.String(128), nullable=False, index=True)
    idempotency_key = db.Column(db.String(128), unique=True, nullable=False)
    months = db.Column(db.Integer, nullable=False, default=1)
    monthly_price_gkach = db.Column(db.Integer, nullable=False, default=500)
    amount_gkach = db.Column(db.Integer, nullable=False)
    room_id = db.Column(db.String(128), nullable=True, index=True)

    user = db.relationship('User', backref='konferans_payments', lazy=True)

    def to_dict(self):
        data = super().to_dict()
        try:
            data['created_at'] = self.created_at.isoformat() if self.created_at else None
        except Exception:
            pass
        return data
