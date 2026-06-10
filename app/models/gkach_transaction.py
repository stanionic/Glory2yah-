"""
GkachTransaction Model - Complete audit trail
"""
from app import db
from app.models.base import BaseModel


class GkachTransaction(BaseModel):
    """Gkach transaction log for audit trail"""
    
    __tablename__ = 'gkach_transactions'
    
    transaction_id = db.Column(db.String(36), unique=True, nullable=False, index=True)
    user_whatsapp = db.Column(db.String(20), nullable=False, index=True)
    
    # Transaction details
    transaction_type = db.Column(db.String(30), nullable=False, index=True)
    # Types: credit, debit, purchase, payment_received, reward, refund, etc.
    
    amount = db.Column(db.Integer, nullable=False)
    old_balance = db.Column(db.Integer)
    new_balance = db.Column(db.Integer)
    
    # Related entities
    related_user = db.Column(db.String(20))  # For transfers
    delivery_id = db.Column(db.String(36), index=True)
    ad_id = db.Column(db.String(36), index=True)
    
    # Metadata
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default='completed', index=True)
    # Status: pending, completed, failed, reversed
    
    meta_data = db.Column(db.Text)  # JSON for additional data
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'transaction_id': self.transaction_id,
            'user_whatsapp': self.user_whatsapp,
            'transaction_type': self.transaction_type,
            'amount': self.amount,
            'old_balance': self.old_balance,
            'new_balance': self.new_balance,
            'related_user': self.related_user,
            'delivery_id': self.delivery_id,
            'ad_id': self.ad_id,
            'description': self.description,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
    
    @classmethod
    def get_user_transactions(cls, whatsapp, limit=50):
        """Get user's recent transactions"""
        return cls.query.filter_by(
            user_whatsapp=whatsapp
        ).order_by(
            cls.created_at.desc()
        ).limit(limit).all()
    
    @classmethod
    def get_transaction_summary(cls, whatsapp):
        """Get transaction summary for user"""
        from sqlalchemy import func
        
        summary = db.session.query(
            cls.transaction_type,
            func.count(cls.id).label('count'),
            func.sum(cls.amount).label('total')
        ).filter_by(
            user_whatsapp=whatsapp,
            status='completed'
        ).group_by(cls.transaction_type).all()
        
        return [
            {
                'type': s.transaction_type,
                'count': s.count,
                'total': s.total
            }
            for s in summary
        ]
    
    def __repr__(self):
        return f'<GkachTransaction {self.transaction_id}: {self.amount}>'
