"""
Delivery Model
"""
from app import db
from app.models.base import BaseModel
from datetime import datetime


class Delivery(BaseModel):
    """Delivery and Transaction tracking model"""
    
    __tablename__ = 'deliveries'
    
    # Override the id from BaseModel - we use delivery_id as primary key
    id = db.Column(db.Integer)  # Not primary key
    
    delivery_id = db.Column(db.String(36), primary_key=True)
    ad_id = db.Column(db.String(36), db.ForeignKey('ads.ad_id'), nullable=True)
    buyer_whatsapp = db.Column(db.String(20), nullable=False, index=True)
    seller_whatsapp = db.Column(db.String(20), nullable=False, index=True)
    
    # Costs
    delivery_cost = db.Column(db.Integer, default=0)  # In Gkach
    total_price = db.Column(db.Integer, nullable=False)  # Ad price + delivery cost
    
    # Status
    status = db.Column(db.String(20), default='negotiating', index=True)
    # negotiating, accepted, confirmed, awaiting_delivery, completed, cancelled
    
    # Verification
    otp = db.Column(db.String(4))
    
    # Dates
    confirmed_at = db.Column(db.DateTime)
    delivered_at = db.Column(db.DateTime)
    delivery_date = db.Column(db.DateTime)
    delivery_date_set_at = db.Column(db.DateTime)
    
    # Content
    cart_items = db.Column(db.Text)  # JSON string for multiple cart items
    delivery_address = db.Column(db.Text)
    delivery_notes = db.Column(db.Text)
    
    # Relationships
    ad = db.relationship('Ad', backref='deliveries')
    
    def to_dict(self):
        """Convert to dictionary"""
        # Audit #6d: prefer normalized junction table; fallback to legacy JSON string
        cart_items_data = []
        try:
            if hasattr(self, 'delivery_items') and self.delivery_items:
                cart_items_data = [di.to_dict() for di in self.delivery_items]
        except Exception:
            pass
        if not cart_items_data:
            import json
            try:
                cart_items_data = json.loads(self.cart_items) if self.cart_items else []
            except:
                cart_items_data = []
            
        return {
            'delivery_id': self.delivery_id,
            'ad_id': self.ad_id,
            'buyer_whatsapp': self.buyer_whatsapp,
            'seller_whatsapp': self.seller_whatsapp,
            'delivery_cost': self.delivery_cost,
            'total_price': self.total_price,
            'status': self.status,
            'cart_items': cart_items_data,
            'delivery_address': self.delivery_address,
            'delivery_date': self.delivery_date.isoformat() if self.delivery_date else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'delivered_at': self.delivered_at.isoformat() if self.delivered_at else None,
        }
    
    def __repr__(self):
        return f'<Delivery {self.delivery_id}: {self.status}>'
