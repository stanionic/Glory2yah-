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
    gkach_charged_total = db.Column(db.Integer, default=0)
    credit_bought_minutes = db.Column(db.Integer, default=0)
    gkach_per_hour = db.Column(db.Integer, default=250)
    free_minutes = db.Column(db.Integer, default=45)
    
    # Relationship
    user = db.relationship('User', backref='konferans_rooms', lazy=True)


class KonferansRecording(BaseModel):
    __tablename__ = 'konferans_recordings'
    
    room_id = db.Column(db.String(128), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True, index=True)
    
    # Optional human title (used by WhatsApp audio-save / title-frame features)
    # New column: safe on fresh DBs via db.create_all(); existing DBs need the
    # idempotent migration script `_migrate_konferans_stream.py` (code always
    # guards with getattr, so a missing column never breaks the app).
    title = db.Column(db.String(255), nullable=True)
    
    def to_dict(self):
        data = super().to_dict()
        try:
            data['url'] = f"/konferans/download_recording/{self.filename}"
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
