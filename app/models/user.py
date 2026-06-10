"""
User Model with Flask-Login integration
"""
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
from app.models.base import BaseModel


class User(UserMixin, BaseModel):
    """User model with authentication"""
    
    __tablename__ = 'users'
    
    # Basic Info
    name = db.Column(db.String(100))
    pseudo = db.Column(db.String(50), unique=True, index=True)
    email = db.Column(db.String(120), unique=True, index=True)
    whatsapp = db.Column(db.String(20), index=True)
    
    # Authentication
    password_hash = db.Column(db.String(255))
    auth_provider = db.Column(db.String(20), default='whatsapp')  # whatsapp, gmail, facebook
    gmail_id = db.Column(db.String(100), unique=True)
    wallet_balance = db.Column(db.Integer, default=0)
    
    # Profile
    profile_photo = db.Column(db.String(255))
    bio = db.Column(db.Text)
    
    # Status
    is_active = db.Column(db.Boolean, default=True, index=True)
    is_admin = db.Column(db.Boolean, default=False)
    email_verified = db.Column(db.Boolean, default=False)
    phone_verified = db.Column(db.Boolean, default=False)
    
    # Timestamps
    last_login = db.Column(db.DateTime)
    
    def set_password(self, password):
        """Hash and set password"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Check password against hash"""
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)
    
    def get_gkach_balance(self):
        """Get user's Gkach balance with caching"""
        from app.services.redis_service import RedisService
        from app import redis_client
        from app.models.user_gkach import UserGkach
        
        if not self.whatsapp:
            return 0
        
        redis_service = RedisService(redis_client)
        
        # Try cache first
        balance = redis_service.get_gkach_balance(self.whatsapp)
        if balance is not None:
            return balance
        
        # Query database
        user_gkach = UserGkach.query.filter_by(user_whatsapp=self.whatsapp).first()
        balance = user_gkach.gkach_balance if user_gkach else 0
        
        # Cache for 5 minutes
        redis_service.set_gkach_balance(self.whatsapp, balance, timeout=300)
        
        return balance
    
    def to_dict(self, include_sensitive=False):
        """Convert to dictionary"""
        data = {
            'id': self.id,
            'name': self.name,
            'pseudo': self.pseudo,
            'email': self.email if include_sensitive else None,
            'whatsapp': self.whatsapp if include_sensitive else None,
            'profile_photo': self.profile_photo,
            'bio': self.bio,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
        return {k: v for k, v in data.items() if v is not None}
    
    def __repr__(self):
        return f'<User {self.pseudo or self.name or self.id}>'
