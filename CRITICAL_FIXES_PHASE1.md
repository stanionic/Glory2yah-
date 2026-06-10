═══════════════════════════════════════════════════════════════════════════════
                    GLORY2YAHPUB - CRITICAL FIXES IMPLEMENTATION
                              PHASE 1 (WEEK 1)
═══════════════════════════════════════════════════════════════════════════════

This document provides exact code fixes for the 6 most critical issues.

═══════════════════════════════════════════════════════════════════════════════
FIX #1: SECURE SECRET KEY MANAGEMENT
═══════════════════════════════════════════════════════════════════════════════

FILE: app.py

BEFORE:
```python
app.config['SECRET_KEY'] = 'glory2yahpub_secret_2024'
```

AFTER:
```python
import secrets

# Generate secure secret key
def get_secret_key():
    secret_key = os.getenv('SECRET_KEY')
    if not secret_key:
        if os.getenv('FLASK_ENV') == 'production':
            raise ValueError("SECRET_KEY environment variable must be set in production")
        # Generate random key for development
        secret_key = secrets.token_hex(32)
        logger.warning(f"Generated temporary SECRET_KEY for development: {secret_key}")
    return secret_key

app.config['SECRET_KEY'] = get_secret_key()
```

FILE: .env
```
SECRET_KEY=your-super-secret-key-here-min-32-chars-long
FLASK_ENV=development
DATABASE_URL=sqlite:///instance/glory2yahpub.db
```

FILE: .env.example
```
SECRET_KEY=change-this-to-a-random-string-in-production
FLASK_ENV=development
DATABASE_URL=sqlite:///instance/glory2yahpub.db
```

═══════════════════════════════════════════════════════════════════════════════
FIX #2: INPUT VALIDATION & SANITIZATION
═══════════════════════════════════════════════════════════════════════════════

FILE: Create utils/validators.py

```python
from flask import request, jsonify
from functools import wraps
import re

class ValidationError(Exception):
    def __init__(self, message, status_code=400):
        self.message = message
        self.status_code = status_code

def validate_pagination(page=None, per_page=None):
    """Validate pagination parameters"""
    page = page or request.args.get('page', 1, type=int)
    per_page = per_page or request.args.get('per_page', 20, type=int)
    
    if page < 1:
        raise ValidationError("Page must be >= 1")
    if per_page < 1 or per_page > 100:
        raise ValidationError("Per page must be between 1 and 100")
    
    return page, per_page

def validate_whatsapp(whatsapp):
    """Validate WhatsApp number format"""
    if not whatsapp or not isinstance(whatsapp, str):
        raise ValidationError("Invalid WhatsApp number")
    
    # Remove non-digits
    clean = re.sub(r'\D', '', whatsapp)
    
    if len(clean) < 10 or len(clean) > 15:
        raise ValidationError("WhatsApp number must be 10-15 digits")
    
    return clean

def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        raise ValidationError("Invalid email format")
    return email.lower()

def validate_price(price):
    """Validate price is positive integer"""
    try:
        price = int(price)
        if price < 0:
            raise ValidationError("Price cannot be negative")
        return price
    except (ValueError, TypeError):
        raise ValidationError("Price must be a valid integer")

def validate_ad_status(status):
    """Validate ad status"""
    valid_statuses = ['under_review', 'approved', 'rejected']
    if status not in valid_statuses:
        raise ValidationError(f"Status must be one of: {', '.join(valid_statuses)}")
    return status

def handle_validation_error(f):
    """Decorator to handle validation errors"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ValidationError as e:
            return jsonify({'success': False, 'error': e.message}), e.status_code
        except Exception as e:
            logger.error(f"Unexpected error in {f.__name__}: {e}")
            return jsonify({'success': False, 'error': 'Internal server error'}), 500
    return decorated_function
```

FILE: app.py (Updated routes)

```python
from utils.validators import (
    validate_pagination, validate_whatsapp, validate_email,
    validate_price, validate_ad_status, handle_validation_error
)

@app.route('/api/ads')
@handle_validation_error
def get_ads():
    page, per_page = validate_pagination()
    
    ads = Ad.query.filter_by(admin_status='approved').order_by(
        Ad.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({
        'success': True,
        'ads': [{'ad_id': ad.ad_id, 'title': ad.title, 'price': ad.price_gkach} 
                for ad in ads.items],
        'total': ads.total,
        'pages': ads.pages,
        'current_page': page
    })
```

═══════════════════════════════════════════════════════════════════════════════
FIX #3: AUTHENTICATION SYSTEM (JWT)
═══════════════════════════════════════════════════════════════════════════════

FILE: Create utils/auth.py

```python
import jwt
import os
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, current_app
import logging

logger = logging.getLogger(__name__)

class AuthError(Exception):
    def __init__(self, message, status_code=401):
        self.message = message
        self.status_code = status_code

def generate_token(user_id, expires_in=86400):
    """Generate JWT token"""
    payload = {
        'user_id': user_id,
        'exp': datetime.utcnow() + timedelta(seconds=expires_in),
        'iat': datetime.utcnow()
    }
    token = jwt.encode(
        payload,
        current_app.config['SECRET_KEY'],
        algorithm='HS256'
    )
    return token

def verify_token(token):
    """Verify JWT token"""
    try:
        payload = jwt.decode(
            token,
            current_app.config['SECRET_KEY'],
            algorithms=['HS256']
        )
        return payload['user_id']
    except jwt.ExpiredSignatureError:
        raise AuthError("Token has expired")
    except jwt.InvalidTokenError:
        raise AuthError("Invalid token")

def get_token_from_request():
    """Extract token from Authorization header"""
    auth_header = request.headers.get('Authorization', '')
    
    if not auth_header.startswith('Bearer '):
        raise AuthError("Missing or invalid Authorization header")
    
    token = auth_header[7:]  # Remove 'Bearer ' prefix
    return token

def require_auth(f):
    """Decorator to require authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            token = get_token_from_request()
            user_id = verify_token(token)
            request.user_id = user_id
            return f(*args, **kwargs)
        except AuthError as e:
            return jsonify({'success': False, 'error': e.message}), e.status_code
    return decorated_function

def require_admin(f):
    """Decorator to require admin role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            token = get_token_from_request()
            user_id = verify_token(token)
            
            # Check if user is admin
            from models import User
            user = User.query.get(user_id)
            if not user or not user.is_admin:
                raise AuthError("Admin access required", 403)
            
            request.user_id = user_id
            return f(*args, **kwargs)
        except AuthError as e:
            return jsonify({'success': False, 'error': e.message}), e.status_code
    return decorated_function
```

FILE: models.py (Add to User model)

```python
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    whatsapp = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(255), nullable=True)
    profile_photo = db.Column(db.String(255), nullable=True)
    bio = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    is_admin = db.Column(db.Boolean, default=False)  # ADD THIS
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = db.Column(db.DateTime, nullable=True)  # ADD THIS
```

FILE: app.py (Add login route)

```python
from utils.auth import generate_token, require_auth, require_admin
from werkzeug.security import generate_password_hash, check_password_hash

@app.route('/api/auth/login', methods=['POST'])
@handle_validation_error
def login():
    data = request.get_json()
    
    if not data or not data.get('whatsapp') or not data.get('password'):
        raise ValidationError("WhatsApp and password required")
    
    whatsapp = validate_whatsapp(data['whatsapp'])
    password = data['password']
    
    user = User.query.filter_by(whatsapp=whatsapp, is_active=True).first()
    
    if not user or not check_password_hash(user.password_hash, password):
        raise ValidationError("Invalid credentials")
    
    token = generate_token(user.id)
    
    return jsonify({
        'success': True,
        'token': token,
        'user': {
            'id': user.id,
            'name': user.name,
            'whatsapp': user.whatsapp,
            'is_admin': user.is_admin
        }
    })

@app.route('/api/auth/register', methods=['POST'])
@handle_validation_error
def register():
    data = request.get_json()
    
    if not data or not data.get('name') or not data.get('whatsapp') or not data.get('password'):
        raise ValidationError("Name, WhatsApp, and password required")
    
    name = data['name'][:100]
    whatsapp = validate_whatsapp(data['whatsapp'])
    password = data['password']
    
    if len(password) < 8:
        raise ValidationError("Password must be at least 8 characters")
    
    if User.query.filter_by(whatsapp=whatsapp).first():
        raise ValidationError("WhatsApp number already registered")
    
    user = User(
        name=name,
        whatsapp=whatsapp,
        password_hash=generate_password_hash(password)
    )
    
    db.session.add(user)
    db.session.commit()
    
    token = generate_token(user.id)
    
    return jsonify({
        'success': True,
        'token': token,
        'user': {
            'id': user.id,
            'name': user.name,
            'whatsapp': user.whatsapp
        }
    }), 201
```

═══════════════════════════════════════════════════════════════════════════════
FIX #4: DATABASE SCHEMA NORMALIZATION
═══════════════════════════════════════════════════════════════════════════════

FILE: models.py (Replace Batch model and add junction table)

BEFORE:
```python
class Batch(db.Model):
    __tablename__ = 'batches'
    batch_id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    ads = db.Column(db.Text, nullable=False)  # WRONG: comma-separated string
```

AFTER:
```python
class Batch(db.Model):
    __tablename__ = 'batches'
    batch_id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    open_graph_data = db.Column(db.Text, nullable=True)
    facebook_share_url = db.Column(db.Text, nullable=True)
    share_count = db.Column(db.Integer, default=0)
    click_rewards = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = db.Column(db.DateTime, nullable=True)
    
    # Relationship to ads through junction table
    ads = db.relationship('Ad', secondary='batch_ads', backref='batches')

class BatchAd(db.Model):
    """Junction table for Batch-Ad relationship"""
    __tablename__ = 'batch_ads'
    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.String(36), db.ForeignKey('batches.batch_id'), nullable=False)
    ad_id = db.Column(db.String(36), db.ForeignKey('ads.ad_id'), nullable=False)
    position = db.Column(db.Integer, default=0)  # For ordering
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('batch_id', 'ad_id', name='uq_batch_ad'),
        db.Index('idx_batch_id', 'batch_id'),
        db.Index('idx_ad_id', 'ad_id'),
    )
```

FILE: models.py (Add indexes to Ad model)

```python
class Ad(db.Model):
    __tablename__ = 'ads'
    # ... existing columns ...
    
    __table_args__ = (
        db.Index('idx_admin_status', 'admin_status'),
        db.Index('idx_created_at', 'created_at'),
        db.Index('idx_user_whatsapp', 'user_whatsapp'),
        db.Index('idx_batch_id', 'batch_id'),
        db.Index('idx_payment_status', 'payment_status'),
    )
```

FILE: models.py (Add soft deletes to all models)

```python
# Add to ALL models:
deleted_at = db.Column(db.DateTime, nullable=True)

# Add helper method to base model or create mixin:
@classmethod
def active(cls):
    """Query only non-deleted records"""
    return cls.query.filter(cls.deleted_at.is_(None))
```

═══════════════════════════════════════════════════════════════════════════════
FIX #5: RATE LIMITING
═══════════════════════════════════════════════════════════════════════════════

FILE: requirements.txt (Add)
```
Flask-Limiter==3.5.0
```

FILE: Create utils/rate_limit.py

```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"  # Use Redis in production
)

# Rate limit strategies
RATE_LIMITS = {
    'login': "5 per minute",
    'register': "3 per minute",
    'api_read': "100 per minute",
    'api_write': "30 per minute",
    'upload': "10 per hour",
}
```

FILE: app.py (Initialize rate limiter)

```python
from utils.rate_limit import limiter, RATE_LIMITS

limiter.init_app(app)

@app.route('/api/auth/login', methods=['POST'])
@limiter.limit(RATE_LIMITS['login'])
@handle_validation_error
def login():
    # ... existing code ...
    pass

@app.route('/api/ads')
@limiter.limit(RATE_LIMITS['api_read'])
@handle_validation_error
def get_ads():
    # ... existing code ...
    pass
```

═══════════════════════════════════════════════════════════════════════════════
FIX #6: SECURITY HEADERS & CORS
═══════════════════════════════════════════════════════════════════════════════

FILE: app.py (Update CORS and add security headers)

```python
from flask_cors import CORS

# Configure CORS properly
CORS(app, resources={
    r"/api/*": {
        "origins": os.getenv('ALLOWED_ORIGINS', 'http://localhost:3000').split(','),
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "supports_credentials": True,
        "max_age": 3600
    }
})

# Add security headers
@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'"
    return response

# Redirect HTTP to HTTPS in production
@app.before_request
def enforce_https():
    if os.getenv('FLASK_ENV') == 'production':
        if request.headers.get('X-Forwarded-Proto', 'http') == 'http':
            url = request.url.replace('http://', 'https://', 1)
            return redirect(url, code=301)
```

FILE: .env (Add)
```
ALLOWED_ORIGINS=https://glory2yahpub.com,https://www.glory2yahpub.com
```

═══════════════════════════════════════════════════════════════════════════════
TESTING THE FIXES
═══════════════════════════════════════════════════════════════════════════════

Test authentication:
```bash
# Register
curl -X POST http://localhost:8080/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"name":"Test User","whatsapp":"+50942882076","password":"SecurePass123"}'

# Login
curl -X POST http://localhost:8080/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"whatsapp":"+50942882076","password":"SecurePass123"}'

# Use token
curl http://localhost:8080/api/ads \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

Test rate limiting:
```bash
# Should work
for i in {1..5}; do curl http://localhost:8080/api/ads; done

# Should be rate limited
for i in {1..10}; do curl http://localhost:8080/api/auth/login; done
```

Test input validation:
```bash
# Should fail
curl "http://localhost:8080/api/ads?page=999999999&per_page=999999999"

# Should work
curl "http://localhost:8080/api/ads?page=1&per_page=20"
```

═══════════════════════════════════════════════════════════════════════════════
DEPLOYMENT CHECKLIST
═══════════════════════════════════════════════════════════════════════════════

Before deploying to production:

□ Set SECRET_KEY environment variable
□ Set FLASK_ENV=production
□ Migrate database schema (add indexes, soft deletes)
□ Test authentication flow
□ Test rate limiting
□ Verify CORS configuration
□ Enable HTTPS
□ Set up monitoring (Sentry)
□ Set up logging aggregation
□ Configure database backups
□ Load test with 100+ concurrent users
□ Security audit with OWASP checklist
□ Penetration testing

═══════════════════════════════════════════════════════════════════════════════
