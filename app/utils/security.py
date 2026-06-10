"""
Security Utilities
CSRF, XSS, SQL Injection protection
"""
import secrets
import hashlib
import hmac
from functools import wraps
from flask import session, abort, request, current_app
import bleach


def generate_csrf_token():
    """Generate CSRF token"""
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return session['_csrf_token']


def validate_csrf_token(token):
    """Validate CSRF token"""
    if '_csrf_token' not in session:
        return False
    return hmac.compare_digest(session['_csrf_token'], token)


def csrf_protect(f):
    """Decorator to protect routes with CSRF"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method == 'POST':
            token = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token')
            if not token or not validate_csrf_token(token):
                abort(403, description="CSRF token missing or invalid")
        return f(*args, **kwargs)
    return decorated_function


def sanitize_html(html_content, allowed_tags=None, allowed_attributes=None):
    """
    Sanitize HTML to prevent XSS
    Returns: cleaned HTML
    """
    if not html_content:
        return ''
    
    if allowed_tags is None:
        allowed_tags = ['p', 'br', 'strong', 'em', 'u', 'a', 'ul', 'ol', 'li']
    
    if allowed_attributes is None:
        allowed_attributes = {'a': ['href', 'title']}
    
    return bleach.clean(
        html_content,
        tags=allowed_tags,
        attributes=allowed_attributes,
        strip=True
    )


def generate_secure_token(length=32):
    """Generate cryptographically secure random token"""
    return secrets.token_urlsafe(length)


def hash_data(data, salt=None):
    """Hash data with optional salt"""
    if salt is None:
        salt = current_app.config['SECRET_KEY']
    
    return hashlib.pbkdf2_hmac(
        'sha256',
        data.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    ).hex()


def verify_signature(data, signature, secret=None):
    """Verify HMAC signature"""
    if secret is None:
        secret = current_app.config['SECRET_KEY']
    
    expected = hmac.new(
        secret.encode('utf-8'),
        data.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected)


def rate_limit_key(prefix='rate_limit'):
    """Generate rate limit key for current request"""
    return f"{prefix}:{request.remote_addr}:{request.endpoint}"


def check_file_signature(file_path, allowed_signatures):
    """
    Check file signature (magic bytes) to verify file type
    Returns: True if valid, False otherwise
    """
    try:
        with open(file_path, 'rb') as f:
            header = f.read(8)
        
        for signature in allowed_signatures:
            if header.startswith(signature):
                return True
        return False
    except Exception as e:
        current_app.logger.error(f"Error checking file signature: {e}")
        return False


# Common file signatures
FILE_SIGNATURES = {
    'jpg': [b'\xFF\xD8\xFF'],
    'png': [b'\x89\x50\x4E\x47'],
    'gif': [b'\x47\x49\x46\x38'],
    'pdf': [b'\x25\x50\x44\x46'],
    'mp4': [b'\x00\x00\x00\x18\x66\x74\x79\x70', b'\x00\x00\x00\x1C\x66\x74\x79\x70'],
}


def admin_required(f):
    """Decorator to require admin access"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin' not in session:
            abort(403, description="Admin access required")
        return f(*args, **kwargs)
    return decorated_function


def login_required_api(f):
    """Decorator for API routes requiring authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask_login import current_user
        if not current_user.is_authenticated:
            return {'error': 'Authentication required'}, 401
        return f(*args, **kwargs)
    return decorated_function


def prevent_sql_injection(query_string):
    """
    Basic SQL injection prevention check
    Returns: True if suspicious, False if safe
    """
    suspicious_patterns = [
        r"(\bUNION\b|\bSELECT\b|\bINSERT\b|\bUPDATE\b|\bDELETE\b|\bDROP\b)",
        r"(--|;|\/\*|\*\/)",
        r"(\bOR\b.*=.*\bOR\b)",
        r"('.*--)",
    ]
    
    import re
    for pattern in suspicious_patterns:
        if re.search(pattern, query_string, re.IGNORECASE):
            current_app.logger.warning(f"Potential SQL injection detected: {query_string}")
            return True
    
    return False


def secure_filename_extended(filename):
    """
    Extended secure filename with timestamp
    Returns: secure unique filename
    """
    from werkzeug.utils import secure_filename
    import time
    
    name = secure_filename(filename)
    timestamp = int(time.time())
    random_suffix = secrets.token_hex(4)
    
    if '.' in name:
        name_part, ext = name.rsplit('.', 1)
        return f"{name_part}_{timestamp}_{random_suffix}.{ext}"
    
    return f"{name}_{timestamp}_{random_suffix}"
