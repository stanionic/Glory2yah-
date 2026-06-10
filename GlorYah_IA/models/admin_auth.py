"""
Admin Authentication for MANDEMMAPBAW
Simple admin login system
"""

import hashlib
import secrets
from functools import wraps
from flask import session, redirect, url_for, request, jsonify

class AdminAuth:
    """Admin authentication handler"""
    
    def __init__(self):
        # Admin credentials
        self.admin_username = "Stan"
        self.admin_password_hash = self._hash_password("StanAi1986")
        self.session_timeout = 3600  # 1 hour
    
    def _hash_password(self, password):
        """Hash password with SHA-256"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def verify_credentials(self, username, password):
        """Verify admin login credentials"""
        if username != self.admin_username:
            return False
        
        password_hash = self._hash_password(password)
        return password_hash == self.admin_password_hash
    
    def login(self, username, password):
        """Login admin user"""
        if self.verify_credentials(username, password):
            # Generate session token
            session['admin_logged_in'] = True
            session['admin_username'] = username
            session['session_token'] = secrets.token_hex(16)
            return True
        return False
    
    def logout(self):
        """Logout admin user"""
        session.pop('admin_logged_in', None)
        session.pop('admin_username', None)
        session.pop('session_token', None)
    
    def is_logged_in(self):
        """Check if admin is logged in"""
        return session.get('admin_logged_in', False)
    
    def get_username(self):
        """Get logged in admin username"""
        return session.get('admin_username', None)

# Singleton instance
_admin_auth = None

def get_admin_auth():
    """Get singleton admin auth instance"""
    global _admin_auth
    if _admin_auth is None:
        _admin_auth = AdminAuth()
    return _admin_auth

def admin_required(f):
    """Decorator to require admin authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth = get_admin_auth()
        
        if not auth.is_logged_in():
            # Check if it's an API request
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': 'Authentication required', 'success': False}), 401
            else:
                return redirect(url_for('admin_login'))
        
        return f(*args, **kwargs)
    return decorated_function
