"""
Mennen M Driver Model
Registered drivers (approved by admin) — replaces hard-coded mock drivers.
"""
from app import db
from app.models.base import BaseModel


class MennemDriver(BaseModel):
    """Mennen M Driver Model."""

    __tablename__ = 'mennem_drivers'

    # Identity
    name = db.Column(db.String(255), nullable=False)
    whatsapp = db.Column(db.String(50), nullable=False, index=True)
    address = db.Column(db.String(255), nullable=False, default='')
    city = db.Column(db.String(120), nullable=False, default='')
    photo = db.Column(db.String(255), nullable=True)

    # Pricing & stats
    base_fare = db.Column(db.Integer, nullable=False, default=150)  # Gkach
    rating = db.Column(db.Float, nullable=False, default=5.0)
    trips_count = db.Column(db.Integer, nullable=False, default=0)

    # Moderation (admin approval workflow)
    is_active = db.Column(db.Boolean, nullable=False, default=False)
    is_verified = db.Column(db.Boolean, nullable=False, default=False)

    def __repr__(self):
        return f'<MennemDriver {self.id} - {self.name} ({self.city})>'