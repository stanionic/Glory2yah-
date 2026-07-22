"""
Configuration Management for Glory2YahPub
Supports: Development, Staging, Production
"""
import os
from datetime import timedelta


class Config:
    """Base configuration"""
    
    # App
    SECRET_KEY = os.environ.get('SECRET_KEY')
    APP_NAME = 'Glory2YahPub'
    
    # Database
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
        'pool_size': 10,
        'max_overflow': 20,
        'pool_timeout': 30,
    }
    
    # Redis
    REDIS_URL = os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'
    
    # Cache
    CACHE_TYPE = 'redis'
    CACHE_REDIS_URL = os.environ.get('REDIS_URL') or 'redis://localhost:6379/1'
    CACHE_DEFAULT_TIMEOUT = 300
    
    # Session
    SESSION_COOKIE_SECURE = False  # For development only
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    
    # File Upload
    UPLOAD_FOLDER = os.path.join('static', 'uploads')
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'webm'}
    ALLOWED_DOCUMENT_EXTENSIONS = {'pdf'}
    
    # Security
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None
    BCRYPT_LOG_ROUNDS = 12
    
    # Rate Limiting
    RATELIMIT_STORAGE_URL = os.environ.get('REDIS_URL') or 'redis://localhost:6379/2'
    RATELIMIT_STRATEGY = 'fixed-window'
    RATELIMIT_DEFAULT = "200 per day, 50 per hour"
    
    # Celery
    CELERY_BROKER_URL = os.environ.get('REDIS_URL') or 'redis://localhost:6379/3'
    CELERY_RESULT_BACKEND = os.environ.get('REDIS_URL') or 'redis://localhost:6379/4'
    
    # Admin
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'glory2yahpub2024')
    ADMIN_WHATSAPP = os.environ.get('ADMIN_WHATSAPP', '+50942882076')
    
    # OAuth
    GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
    GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')
    
    # Business Logic
    GKACH_REWARD_AMOUNT = 100
    GKACH_CLICKS_REQUIRED = 100
    AUTO_SLIDE_INTERVAL = 2000  # milliseconds
    # Gkach Exchange Rate: 100 Gkach = 120 Gourdes
    GKACH_TO_HTG_RATE = 1.2  # 1 Gkach = 1.2 HTG
    
    # Pagination
    ITEMS_PER_PAGE = 20
    MAX_ITEMS_PER_PAGE = 100
    
    # Logging
    LOG_LEVEL = 'INFO'
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Sentry (Error Tracking)
    SENTRY_DSN = os.environ.get('SENTRY_DSN', '')

    def __init__(self):
        # Global validation: Ensure REDIS_URL is not pointing to localhost in non-dev envs only if provided
        pass


import secrets
import os

def _load_secret_key():
    """Load or generate a persistent secret key"""
    key = os.environ.get('SECRET_KEY')
    if key and key != 'your-secret-key-here-change-this-in-production':
        return key
    secret_key_file = '.flask_secret_key'
    if os.path.exists(secret_key_file):
        with open(secret_key_file, 'r') as f:
            return f.read().strip()
    key = secrets.token_hex(32)
    with open(secret_key_file, 'w') as f:
        f.write(key)
    return key


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    TESTING = False

    SECRET_KEY = _load_secret_key()

    # Use PostgreSQL if DATABASE_URL is set, otherwise SQLite
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        os.environ.get('DEV_DATABASE_URL') or \
        'sqlite:///glory2yahpub_dev.db'

    # Disable HTTPS requirements
    SESSION_COOKIE_SECURE = False

    # Fallback to simple cache when Redis not available
    CACHE_TYPE = 'simple'
    RATELIMIT_STORAGE_URL = 'memory://'


class TestingConfig(Config):
    """Testing configuration"""
    DEBUG = True
    TESTING = True
    
    SECRET_KEY = _load_secret_key()
    
    # Use in-memory SQLite for tests  (pool options not supported by SQLite)
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
    }
    
    # Use fake Redis for tests
    CACHE_TYPE = 'simple'
    
    # Disable CSRF for testing
    WTF_CSRF_ENABLED = False
    
    # Disable rate limiting for tests
    RATELIMIT_ENABLED = False


class StagingConfig(Config):
    """Staging configuration"""
    DEBUG = False
    TESTING = False
    
    # PostgreSQL for staging
    SQLALCHEMY_DATABASE_URI = os.environ.get('STAGING_DATABASE_URL') or \
        None


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    TESTING = False
    
    # Production-only Overrides
    REDIS_URL = os.environ.get('REDIS_URL')
    CACHE_REDIS_URL = os.environ.get('REDIS_URL')
    RATELIMIT_STORAGE_URL = os.environ.get('REDIS_URL')
    CELERY_BROKER_URL = os.environ.get('REDIS_URL')
    CELERY_RESULT_BACKEND = os.environ.get('REDIS_URL')

    # Strict security
    SESSION_COOKIE_SECURE = True
    
    # Production logging
    LOG_LEVEL = 'WARNING'

    def __init__(self):
        # Enforce PostgreSQL and Secret Key in Production
        super().__init__()
        db_url = os.environ.get('DATABASE_URL')
        if db_url and db_url.startswith('postgres://'):
            db_url = db_url.replace('postgres://', 'postgresql://', 1)
        self.SQLALCHEMY_DATABASE_URI = db_url
        
        if not self.SECRET_KEY:
            raise ValueError("CRITICAL: SECRET_KEY must be set in production environment!")
        if not self.SQLALCHEMY_DATABASE_URI or 'sqlite' in self.SQLALCHEMY_DATABASE_URI.lower():
            raise ValueError("CRITICAL: DATABASE_URL must be a PostgreSQL connection string in production!")
        
        # Fallback if no Redis
        if not self.REDIS_URL:
            self.CACHE_TYPE = 'simple'
            self.SESSION_TYPE = 'filesystem'
            self.SESSION_FILE_DIR = '.flask_session'
            self.RATELIMIT_STORAGE_URL = 'memory://'


# Configuration dictionary
config_dict = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'staging': StagingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}


def get_config(env=None):
    """Get configuration based on environment"""
    if env is None:
        env = os.environ.get('FLASK_ENV', 'development')
    return config_dict.get(env, config_dict['default'])
