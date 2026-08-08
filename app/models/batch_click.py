"""
BatchClick Model
Tracks UNIQUE clicks on a shared ad batch link.

Uniqueness rule (anti-fraud):
A given person (clicker) counts at most ONCE per referrer per batch, enforced
by a database unique constraint on (batch_id, referrer_whatsapp, clicker_whatsapp).
This guarantees "chaque clic vient d'une personne unique" — a clicker cannot
inflate a referrer's count by clicking repeatedly, across sessions or over days.
"""
from app import db
from app.models.base import BaseModel


class BatchClick(BaseModel):
    """A single unique click recorded for a referrer on a shared batch."""

    __tablename__ = 'batch_clicks'

    batch_id = db.Column(db.String(36), nullable=False, index=True)
    # The user who SHARED the link (receives the Admin reward)
    referrer_whatsapp = db.Column(db.String(20), nullable=False, index=True)
    # The unique person who CLICKED the shared link
    clicker_whatsapp = db.Column(db.String(20), nullable=False, index=True)
    # The IP of the clicker (anti-fraud: limited clicks per IP)
    clicker_ip = db.Column(db.String(45), nullable=True, index=True)
    # The signed device/browser id of the clicker (anti-fraud: limited per device)
    clicker_device = db.Column(db.String(64), nullable=True, index=True)

    # Uniqueness: one unique click per (batch, referrer, clicker)
    __table_args__ = (
        db.UniqueConstraint(
            'batch_id', 'referrer_whatsapp', 'clicker_whatsapp',
            name='_batch_clicks_unique_uc'
        ),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'batch_id': self.batch_id,
            'referrer_whatsapp': self.referrer_whatsapp,
            'clicker_whatsapp': self.clicker_whatsapp,
            'clicker_ip': self.clicker_ip,
            'clicker_device': self.clicker_device,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
