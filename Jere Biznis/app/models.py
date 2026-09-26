from datetime import datetime, timezone
from .extensions import db

def utcnow():
    return datetime.now(timezone.utc)

class Institution(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    institution_type = db.Column(db.String(80), nullable=False)
    owner_user_id = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

class Membership(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    institution_id = db.Column(db.Integer, db.ForeignKey("institution.id"), nullable=False, index=True)
    user_id = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(40), nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)

class Subscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    institution_id = db.Column(db.Integer, db.ForeignKey("institution.id"), unique=True, nullable=False)
    status = db.Column(db.String(30), default="TRIAL", nullable=False)
    monthly_price_gkach = db.Column(db.Integer, default=500, nullable=False)
    trial_start = db.Column(db.DateTime(timezone=True), nullable=False)
    trial_end = db.Column(db.DateTime(timezone=True), nullable=False)
    subscription_start = db.Column(db.DateTime(timezone=True))
    expiration = db.Column(db.DateTime(timezone=True))
    last_verified_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    institution_id = db.Column(db.Integer, db.ForeignKey("institution.id"), nullable=False, index=True)
    transaction_id = db.Column(db.String(128), unique=True, nullable=False)
    idempotency_key = db.Column(db.String(128), unique=True, nullable=False)
    months = db.Column(db.Integer, nullable=False)
    monthly_price_gkach = db.Column(db.Integer, nullable=False)
    amount_gkach = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    institution_id = db.Column(db.Integer, nullable=False, index=True)
    event_type = db.Column(db.String(100), nullable=False)
    actor_user_id = db.Column(db.String(128))
    metadata_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

class SyncOperation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    operation_id = db.Column(db.String(128), unique=True, nullable=False)
    institution_id = db.Column(db.Integer, nullable=False, index=True)
    device_id = db.Column(db.String(128), nullable=False)
    user_id = db.Column(db.String(128), nullable=False)
    entity_type = db.Column(db.String(100), nullable=False)
    entity_id = db.Column(db.String(128), nullable=False)
    operation_type = db.Column(db.String(20), nullable=False)
    payload = db.Column(db.Text, nullable=False)
    local_version = db.Column(db.Integer, default=1, nullable=False)
    base_version = db.Column(db.Integer, default=0, nullable=False)
    checksum = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

class Backup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    institution_id = db.Column(db.Integer, nullable=False, index=True)
    backup_id = db.Column(db.String(128), unique=True, nullable=False)
    ciphertext_sha256 = db.Column(db.String(128), nullable=False)
    size_bytes = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
