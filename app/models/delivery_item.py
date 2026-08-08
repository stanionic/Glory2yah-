"""
DeliveryItem Model - Junction table for Delivery cart items (Audit #6d)
Normalizes Delivery.cart_items (was JSON string) into a proper relational table.
"""
from app import db
from app.models.base import BaseModel


class DeliveryItem(BaseModel):
    """Junction table linking a Delivery to its cart items (1NF normalization)"""

    __tablename__ = 'delivery_items'

    delivery_id = db.Column(db.String(36), db.ForeignKey('deliveries.delivery_id'), nullable=False, index=True)
    ad_id = db.Column(db.String(36), db.ForeignKey('ads.ad_id'), nullable=False, index=True)
    quantity = db.Column(db.Integer, default=1, nullable=False)
    price_gkach = db.Column(db.Integer, default=0, nullable=False)  # Snapshot of ad price at purchase time
    shipping_fee = db.Column(db.Float, default=0.0, nullable=False)

    # Relationships
    delivery = db.relationship('Delivery', backref='delivery_items')
    ad = db.relationship('Ad', backref='delivery_entries')

    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'delivery_id': self.delivery_id,
            'ad_id': self.ad_id,
            'quantity': self.quantity,
            'price_gkach': self.price_gkach,
            'shipping_fee': self.shipping_fee,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f'<DeliveryItem {self.delivery_id}: {self.ad_id} x{self.quantity}>'
