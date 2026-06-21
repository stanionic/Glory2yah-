from app import db
from datetime import datetime
import uuid


class Party(db.Model):
    """Party model"""
    __tablename__ = 'parties'
    
    party_id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    date = db.Column(db.Date, nullable=False)
    location = db.Column(db.String(200), nullable=True)
    price = db.Column(db.Integer, default=0)
    photo = db.Column(db.String(255), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # Link to User
    owner_code = db.Column(db.String(6), nullable=True)  # 6-digit code for owner reconnection
    food_options = db.Column(db.Text, nullable=True)  # JSON array
    drink_options = db.Column(db.Text, nullable=True)  # JSON array
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    participants = db.relationship('PartyParticipant', backref='party', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Party {self.name}>'


class PartyParticipant(db.Model):
    """Party Participant model"""
    __tablename__ = 'party_participants'
    
    participant_id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    party_id = db.Column(db.String(36), db.ForeignKey('parties.party_id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # Link to User
    name = db.Column(db.String(100), nullable=False)
    whatsapp = db.Column(db.String(20), nullable=False)
    food_choice = db.Column(db.String(100), nullable=True)
    drink_choice = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<PartyParticipant {self.name}>'