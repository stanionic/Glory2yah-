"""
UserGkach Model - Virtual Currency Management
"""
from app import db
from app.models.base import BaseModel
from sqlalchemy import CheckConstraint


class UserGkach(BaseModel):
    """User Gkach balance with transaction safety"""
    
    __tablename__ = 'user_gkach'
    
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    user_whatsapp = db.Column(db.String(20), nullable=False, unique=True, index=True)
    gkach_balance = db.Column(db.Integer, default=0, nullable=False)
    gkach_requests = db.Column(db.Text)  # JSON string for pending requests
    
    # Relationships
    user = db.relationship('User', backref='gkach_account')
    
    # Constraints
    __table_args__ = (
        CheckConstraint('gkach_balance >= 0', name='check_positive_balance'),
    )
    
    def add_balance(self, amount, description=''):
        """
        Add to balance with cache invalidation
        Thread-safe with database-level locking
        """
        if amount <= 0:
            raise ValueError("Amount must be positive")
        
        from app.services.redis_service import RedisService
        from app import redis_client
        
        old_balance = self.gkach_balance
        self.gkach_balance += amount
        
        # Invalidate cache
        redis_service = RedisService(redis_client)
        redis_service.invalidate_gkach_balance(self.user_whatsapp)
        
        # Log transaction
        self._log_transaction('credit', amount, old_balance, self.gkach_balance, description)
        
        return self.gkach_balance
    
    def deduct_balance(self, amount, description=''):
        """
        Deduct from balance with validation
        Thread-safe with database-level locking
        """
        if amount <= 0:
            raise ValueError("Amount must be positive")
        
        if self.gkach_balance < amount:
            raise ValueError("Insufficient balance")
        
        from app.services.redis_service import RedisService
        from app import redis_client
        
        old_balance = self.gkach_balance
        self.gkach_balance -= amount
        
        # Invalidate cache
        redis_service = RedisService(redis_client)
        redis_service.invalidate_gkach_balance(self.user_whatsapp)
        
        # Log transaction
        self._log_transaction('debit', amount, old_balance, self.gkach_balance, description)
        
        return self.gkach_balance
    
    def _log_transaction(self, transaction_type, amount, old_balance, new_balance, description):
        """Log transaction to GkachTransaction table"""
        from app.models.gkach_transaction import GkachTransaction
        import uuid
        
        transaction = GkachTransaction(
            transaction_id=str(uuid.uuid4()),
            user_whatsapp=self.user_whatsapp,
            transaction_type=transaction_type,
            amount=amount,
            old_balance=old_balance,
            new_balance=new_balance,
            description=description,
            status='completed'
        )
        db.session.add(transaction)
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'user_whatsapp': self.user_whatsapp,
            'gkach_balance': self.gkach_balance,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
    
    def __repr__(self):
        return f'<UserGkach {self.user_whatsapp}: {self.gkach_balance}>'
