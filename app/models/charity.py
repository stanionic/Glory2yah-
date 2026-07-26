"""
Charity Donation Model
Track donations for charitable causes during checkout
"""
from app import db
from app.models.base import BaseModel
from datetime import datetime


class CharityDonation(BaseModel):
    """Model for tracking charitable donations made during purchases"""
    
    __tablename__ = 'charity_donations'
    
    donation_id = db.Column(db.String(36), unique=True, nullable=False, index=True)
    donor_whatsapp = db.Column(db.String(20), nullable=False, index=True)
    delivery_id = db.Column(db.String(36), db.ForeignKey('deliveries.delivery_id'), nullable=True)
    
    # Donation details
    amount_gkach = db.Column(db.Integer, nullable=False, default=0)
    cause = db.Column(db.String(100), default='general')  # general, education, health, community
    message = db.Column(db.Text, nullable=True)
    
    # Status
    status = db.Column(db.String(20), default='completed')  # pending, completed, refunded
    
    # Tracking
    donor_name = db.Column(db.String(100), nullable=True)
    is_anonymous = db.Column(db.Boolean, default=False)
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'donation_id': self.donation_id,
            'donor_whatsapp': self.donor_whatsapp,
            'delivery_id': self.delivery_id,
            'amount_gkach': self.amount_gkach,
            'cause': self.cause,
            'message': self.message,
            'status': self.status,
            'donor_name': self.donor_name,
            'is_anonymous': self.is_anonymous,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
    
    def __repr__(self):
        return f'<CharityDonation {self.donation_id}: {self.amount_gkach} Gkach for {self.cause}>'


class CharityCause(db.Model):
    """Model for defining charitable causes"""
    
    __tablename__ = 'charity_causes'
    
    id = db.Column(db.Integer, primary_key=True)
    cause_id = db.Column(db.String(36), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    icon = db.Column(db.String(10), default='❤️')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'cause_id': self.cause_id,
            'name': self.name,
            'description': self.description,
            'icon': self.icon,
            'is_active': self.is_active,
        }
    
    def __repr__(self):
        return f'<CharityCause {self.name}>'
