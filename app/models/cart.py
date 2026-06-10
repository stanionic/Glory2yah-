"""
CartItem Model
"""
from app import db
from app.models.base import BaseModel


class CartItem(BaseModel):
    """Cart item model"""
    
    __tablename__ = 'cart_items'
    
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    product_id = db.Column(db.String(36), db.ForeignKey('ads.ad_id'), index=True)
    quantity = db.Column(db.Integer, default=1)
    shipping_fee_set = db.Column(db.Boolean, default=False)
    shipping_fee = db.Column(db.Float, default=0.0)
    negotiation_status = db.Column(db.String(20), default='cart')  # cart, buyer_submitted, seller_updated
    cart_id = db.Column(db.String(36), nullable=True)  # Unique ID for each cart submission
    delivery_address = db.Column(db.Text, nullable=True)
    
    # Relationships
    user = db.relationship('User', backref='cart_items')
    ad = db.relationship('Ad', backref='cart_entries')
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'product_id': self.product_id,
            'quantity': self.quantity,
            'shipping_fee': self.shipping_fee,
            'negotiation_status': self.negotiation_status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
