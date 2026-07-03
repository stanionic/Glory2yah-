"""
Mennen M Trip Model
"""
from datetime import datetime
from app import db
from app.models.base import BaseModel

class MennemTrip(BaseModel):
    """Mennen M Trip Model"""
    
    __tablename__ = 'mennem_trips'
    
    # Trip details
    from_location = db.Column(db.String(255), nullable=False)
    to_location = db.Column(db.String(255), nullable=False)
    price_gkach = db.Column(db.Integer, nullable=False)
    
    # Driver details
    driver_name = db.Column(db.String(255), nullable=False)
    driver_phone = db.Column(db.String(50), nullable=False)
    driver_rating = db.Column(db.Float, default=0.0)
    
    # Passenger details
    passenger_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    passenger_whatsapp = db.Column(db.String(50), nullable=False)
    
    # Trip status
    status = db.Column(db.String(50), default='pending', nullable=False) # pending, paid, completed, cancelled
    
    # Relationships
    passenger = db.relationship('User', backref='mennem_trips')
    
    def __repr__(self):
        return f'<MennemTrip {self.id} - {self.from_location} to {self.to_location}>'
