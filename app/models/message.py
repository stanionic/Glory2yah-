"""
Message Model - Chat between buyer and seller
"""
from app import db
from app.models.base import BaseModel


class Message(BaseModel):
    """Chat message for delivery negotiation"""
    
    __tablename__ = 'messages'
    
    delivery_id = db.Column(db.String(36), db.ForeignKey('deliveries.delivery_id'), nullable=False, index=True)
    sender_whatsapp = db.Column(db.String(20), nullable=False, index=True)
    message = db.Column(db.Text, nullable=False)
    
    # Relationships
    delivery = db.relationship('Delivery', backref='messages')
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'delivery_id': self.delivery_id,
            'sender_whatsapp': self.sender_whatsapp,
            'message': self.message,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
    
    def __repr__(self):
        return f'<Message {self.id} from {self.sender_whatsapp}>'
