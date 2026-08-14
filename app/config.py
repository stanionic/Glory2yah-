"""
Configuration Management for Glory2YahPub
Supports: Development, Staging, Production
"""
import os
import secrets
from datetime import timedelta


def _instance_dir():
    """Return the Flask instance/ directory path (persistent disk mount point on Render).
    On Render: render.yaml mounts 1GB disk at /opt/render/project/src/instance.
    By using instance/ as the root for all mutable data, we get persistence for free.
    """
    import os as _os
    here = _os.path.dirname(_os.path.abspath(__file__))  # app/
    project_root = _os.path.dirname(here)                 # project root
    inst_dir = _os.environ.get('INSTANCE_DIR', _os.path.join(project_root, 'instance'))
    try:
        _os.makedirs(inst_dir, exist_ok=True)
    except Exception:
        pass
    return inst_dir


def _on_render():
    """Heuristic: are we running on Render.com PaaS?"""
    import os as _os
    return bool(
        _os.environ.get('RENDER') or
        _os.environ.get('RENDER_SERVICE_ID') or
        _os.environ.get('RENDER_EXTERNAL_URL') or
        (_os.environ.get('PORT') and _os.environ.get('PORT') != '5000')
    )


def _load_secret_key():
    """Load or generate a persistent SECRET_KEY (never None).
    Priority: env SECRET_KEY > instance/.flask_secret_key (persistent) > cwd/.flask_secret_key.
    """
    env_key = os.environ.get('SECRET_KEY', '')
    weak = ('', 'your-secret-key-here-change-this-in-production', 'None', None)
    if env_key not in weak:
        return env_key
    inst_dir = _instance_dir()
    candidates = [
        os.path.join(inst_dir, '.flask_secret_key'),
        '.flask_secret_key',
    ]
    for secret_key_file in candidates:
        if os.path.exists(secret_key_file):
            try:
                with open(secret_key_file, 'r') as f:
                    data = f.read().strip()
                    if data:
                        return data
            except Exception:
                pass
    key = secrets.token_hex(32)
    try:
        with open(candidates[0], 'w') as f:
            f.write(key)
    except Exception:
        try:
            with open(candidates[1], 'w') as f:
                f.write(key)
        except Exception:
            pass
    return key

def _normalize_database_url(url=None):
    """None/empty-safe DSN normalization.

    - Render legacy 'postgres://' → 'postgresql://' (required by SQLAlchemy 1.4+).
    - Optionally appends '?sslmode=...' from DATABASE_SSLMODE when the URL does
      not already carry an sslmode parameter (Render external / Neon / Supabase).
    """
    if not url:
        return url
    url = url.strip()
    if url.startswith('postgres://'):
        url = 'postgresql://' + url[len('postgres://'):]
    ssl = os.environ.get('DATABASE_SSLMODE', '').strip()
    if url.startswith('postgresql://') and ssl and 'sslmode=' not in url:
        url = url + ('&' if '?' in url else '?') + 'sslmode=' + ssl
    return url


def _is_postgres_url(url=None):
    """True when the DSN targets PostgreSQL (postgresql://...)."""
    return bool(url and url.lower().startswith('postgresql://'))


def _engine_options_for(url=None):
    """Return SQLAlchemy engine options tuned for the resolved DB URL.

    PostgreSQL: gunicorn runs 4 workers, EACH with its own SQLAlchemy pool, so we
    keep the per-worker pool small — 4 workers x (pool_size + max_overflow) =
    4 x 10 = 40 connections worst-case, safely inside Render Postgres limits.
    `pool_pre_ping` + `pool_recycle` avoid stale connections after DB restarts;
    `connect_timeout` + TCP keepalives fail fast instead of hanging on a dead host.
    SQLite: mirrors the historical base defaults so existing dev behaviour is unchanged.
    """
    if _is_postgres_url(url):
        pool_size = int(os.environ.get('DB_POOL_SIZE', '4'))
        max_overflow = int(os.environ.get('DB_MAX_OVERFLOW', '6'))
        return {
            'pool_pre_ping': True,
            'pool_recycle': 300,
            'pool_size': pool_size,
            'max_overflow': max_overflow,
            'pool_timeout': 30,
            'connect_args': {
                'connect_timeout': 10,
                'keepalives': 1,
                'keepalives_idle': 60,
                'keepalives_interval': 15,
                'keepalives_count': 5,
            },
        }
    return {
        'pool_pre_ping': True,
        'pool_recycle': 300,
        'pool_size': 10,
        'max_overflow': 20,
        'pool_timeout': 30,
    }

class Config:
    """Base configuration.

    PERSISTENCE PRINCIPLE (Render deploy safety):
      All mutable user data paths default under INSTANCE_DIR = project/instance
      On Render.com render.yaml mounts a 1GB persistent disk at:
        mountPath: /opt/render/project/src/instance
      Therefore uploads, sessions, SQLite fallback, logs, flask_secret_key
      ALL survive rebuilds / deploys / commits by default.
      Env-var overrides exist for every path (UPLOAD_FOLDER, SESSION_FILE_DIR,
      INSTANCE_DIR, DATABASE_URL) if operators want to relocate them.

    NOTE: environment variables are read IN __init__() (per-instance) so that
    get_config() returns a live instance — Flask.config.from_object() then
    picks up the freshly-computed values. This fixes a bug where class-body
    os.environ reads happen at module-import time and were stale / not
    overridable by tests setting env vars mid-process.
    """

    # -------- Class-level DEFAULT values (can be overridden per instance) --------
    _INSTANCE_DIR_DEFAULT = None  # computed lazy
    _ON_RENDER_DEFAULT = None

    APP_NAME = 'Glory2YahPub'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
        'pool_size': 10,
        'max_overflow': 20,
        'pool_timeout': 30,
    }

    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)

    MAX_CONTENT_LENGTH = 100 * 1024 * 1024
    ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'webm'}
    ALLOWED_DOCUMENT_EXTENSIONS = {'pdf'}

    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None
    WTF_CSRF_SSL_CHECKS = False
    WTF_CSRF_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}
    WTF_CSRF_HEADERS = ['X-CSRFToken', 'X-CSRF-Token']
    BCRYPT_LOG_ROUNDS = 12

    RATELIMIT_STRATEGY = 'fixed-window'
    RATELIMIT_DEFAULT = "200 per day, 50 per hour"

    GKACH_REWARD_AMOUNT = 10
    GKACH_CLICKS_REQUIRED = 100
    GKACH_MAX_CLICKS_PER_IP = 3
    GKACH_MAX_CLICKS_PER_DEVICE = 1
    AUTO_SLIDE_INTERVAL = 2000
    GKACH_TO_HTG_RATE = 1.2

    ITEMS_PER_PAGE = 20
    MAX_ITEMS_PER_PAGE = 100

    LOG_LEVEL = 'INFO'
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    SENTRY_DSN = ''

    def __init__(self):
        """Fully evaluate all env-dependent config values per instance.
        Called by get_config() via cls() so Flask receives a populated
        object where values reflect the CURRENT state of os.environ.
        """
        inst_dir = _instance_dir()
        on_render = _on_render()
        # Persistent paths under <instance>/ (Render persistent disk mount)
        self.INSTANCE_DIR = inst_dir
        self.ON_RENDER = on_render
        # SECRET_KEY — never None (env > instance file > cwd file > auto)
        self.SECRET_KEY = _load_secret_key()
        # Redis — default localhost dev, override via env
        redis_url = os.environ.get('REDIS_URL')
        self.REDIS_URL = redis_url or 'redis://localhost:6379/0'
        # Cache
        self.CACHE_TYPE = 'redis'
        self.CACHE_REDIS_URL = redis_url or 'redis://localhost:6379/1'
        self.CACHE_DEFAULT_TIMEOUT = 300
        # Sessions — filesystem fallback ON PERSISTENT DISK by default
        self.SESSION_TYPE = os.environ.get('SESSION_TYPE', 'filesystem')
        self.SESSION_FILE_DIR = os.environ.get(
            'SESSION_FILE_DIR', os.path.join(inst_dir, '.flask_session')
        )
        self.SESSION_PERMANENT = True
        try:
            os.makedirs(self.SESSION_FILE_DIR, exist_ok=True)
        except Exception:
            pass
        # File Upload — ENV OVERRIDE wins, else Render=instance/uploads, else static/uploads
        env_up = os.environ.get('UPLOAD_FOLDER')
        if env_up:
            self.UPLOAD_FOLDER = env_up
        elif on_render:
            self.UPLOAD_FOLDER = os.path.join(inst_dir, 'uploads')
        else:
            self.UPLOAD_FOLDER = os.path.join('static', 'uploads')
        try:
            os.makedirs(self.UPLOAD_FOLDER, exist_ok=True)
        except Exception:
            pass
        # ----- Staging & Backup (extra Render persistence belt + suspenders) -----
        # Staging = PRE-POSTGRES landing zone (raw bytes, validated, moved to UPLOAD_FOLDER
        # only AFTER extension/size/MIME-hash checks pass.  Garbage-collected after 30 days.
        # Backup  = POST-upload mirror copy — same disk/FS (snapshot every successful commit).
        # These two folders MUST also be excluded from .gitignore (see project root .gitignore)
        env_stage = os.environ.get('STAGING_UPLOAD_FOLDER')
        if env_stage:
            self.STAGING_UPLOAD_FOLDER = env_stage
        else:
            self.STAGING_UPLOAD_FOLDER = os.path.join(inst_dir, 'uploads_staging')
        env_backup = os.environ.get('BACKUP_UPLOAD_FOLDER')
        if env_backup:
            self.BACKUP_UPLOAD_FOLDER = env_backup
        else:
            self.BACKUP_UPLOAD_FOLDER = os.path.join(inst_dir, 'uploads_backup')
        for _p in (self.STAGING_UPLOAD_FOLDER, self.BACKUP_UPLOAD_FOLDER):
            try:
                os.makedirs(_p, exist_ok=True)
            except Exception:
                pass
        # Marker file that lives on the Render persistent disk (same directory tree).
        # At boot: if file does not exist AND we're on Render → WARN LOUD that the
        # persistent disk mount is missing and uploads WILL be erased on next deploy.
        self.PERSISTENCE_MARKER_FILE = os.path.join(inst_dir, '.uploads_persistent_marker.txt')
        # Staging file TTL: cleanup cron (or boot cleanup) deletes staging files > N days.
        self.STAGING_TTL_DAYS = int(os.environ.get('STAGING_TTL_DAYS', '30'))
        # Logging directory — default on persistent disk
        self.LOG_DIR = os.environ.get('LOG_DIR', os.path.join(inst_dir, 'logs'))
        try:
            os.makedirs(self.LOG_DIR, exist_ok=True)
        except Exception:
            pass
        # Rate limiting
        self.RATELIMIT_STORAGE_URL = redis_url or 'redis://localhost:6379/2'
        # Celery
        self.CELERY_BROKER_URL = redis_url or 'redis://localhost:6379/3'
        self.CELERY_RESULT_BACKEND = redis_url or 'redis://localhost:6379/4'
        # Admin credentials
        self.ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'StanGlory2YahPub1986')
        self.ADMIN_WHATSAPP = os.environ.get('ADMIN_WHATSAPP', '+50942882076')
        self.ADMIN_PSEUDO = os.environ.get('ADMIN_PSEUDO', 'Admin509')
        self.ADMIN_NAME = os.environ.get('ADMIN_NAME', 'Glory2YahPub')
        # OAuth
        self.GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
        self.GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')
        # Sentry
        self.SENTRY_DSN = os.environ.get('SENTRY_DSN', '')


class DevelopmentConfig(Config):
    """Development configuration.
    SQLite in instance/ for persistence across restarts; env DATABASE_URL overrides to Postgres.
    """
    DEBUG = True
    TESTING = False

    # Static dev-only defaults (env-dependent bits live in __init__)
    SESSION_COOKIE_SECURE = False

    def __init__(self):
        super().__init__()
        inst_dir = _instance_dir()
        # DB: PostgreSQL (DATABASE_URL env) OR legacy DEV_DATABASE_URL OR local SQLite persistent
        db_url = _normalize_database_url(
            os.environ.get('DATABASE_URL') or os.environ.get('DEV_DATABASE_URL')
        ) or 'sqlite:///' + os.path.join(inst_dir, 'glory2yahpub_dev.db')
        self.SQLALCHEMY_DATABASE_URI = db_url
        self.SQLALCHEMY_ENGINE_OPTIONS = _engine_options_for(db_url)
        # Local dev: no real Redis available -> simple cache + memory rate-limit
        if not os.environ.get('REDIS_URL'):
            self.CACHE_TYPE = 'simple'
            self.RATELIMIT_STORAGE_URL = 'memory://'
        # Optional env override to disable rate-limits (useful for local load tests)
        self.RATELIMIT_ENABLED = (
            os.environ.get('RATELIMIT_ENABLED', '1')
            not in ('0', 'false', 'False', 'no', 'off')
        )


class TestingConfig(Config):
    """Testing configuration — in-memory DB, CSRF/rate-limits disabled."""
    DEBUG = True
    TESTING = True

    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_ENGINE_OPTIONS = {'pool_pre_ping': True}
    CACHE_TYPE = 'simple'
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False

    def __init__(self):
        super().__init__()


class StagingConfig(Config):
    """Staging configuration — PostgreSQL required via STAGING_DATABASE_URL or DATABASE_URL."""
    DEBUG = False
    TESTING = False

    def __init__(self):
        super().__init__()
        db_url = _normalize_database_url(
            os.environ.get('STAGING_DATABASE_URL') or
            os.environ.get('DATABASE_URL')
        )
        if not db_url or not _is_postgres_url(db_url):
            raise ValueError(
                'CRITICAL: STAGING_DATABASE_URL (or DATABASE_URL) must be a '
                'PostgreSQL connection string in staging — SQLite is not allowed.'
            )
        self.SQLALCHEMY_DATABASE_URI = db_url
        self.SQLALCHEMY_ENGINE_OPTIONS = _engine_options_for(db_url)


class ProductionConfig(Config):
    """Production configuration.

    CRITICAL REQUIREMENTS (enforced here; raise ValueError if violated):
      - DATABASE_URL must be set and MUST be PostgreSQL (NOT SQLite)
      - SECRET_KEY must be set (never None / weak / placeholder)

    Render convention:
      - postgres:// URLs (Render Dashboard default) are auto-converted to
        postgresql:// (required by SQLAlchemy 1.4+)
    """
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    LOG_LEVEL = 'WARNING'

    def __init__(self):
        super().__init__()
        inst_dir = _instance_dir()
        on_render = _on_render()

        # ----- PostgreSQL DSN normalization (Render legacy postgres:// → postgresql://) -----
        raw_db_url = os.environ.get('DATABASE_URL')
        db_url = _normalize_database_url(raw_db_url)

        # ----- Render-managed DB race-condition safety -----
        # On Render the very first deploy can start the web container BEFORE the
        # managed PostgreSQL `fromDatabase` injection is fully propagated (env
        # var temporarily empty/unset). We MUST NOT hard-crash in that window,
        # otherwise the deploy gets stuck in a restart loop even after PG is
        # ready. Instead we:
        #   1. Fall back to a PERSISTENT SQLite file on the Render instance disk
        #      (NOT the ephemeral container FS) — this guarantees NO DATA LOSS
        #      across restarts/deploys while PG is still coming up.
        #   2. Log a huge CRITICAL warning so the Render dashboard shows
        #      immediately that DATABASE_URL is missing and needs attention.
        #   3. Allow opting back into the strict hard-crash guard with
        #      DB_ENFORCE_POSTGRES_PRODUCTION=1 (for CICD/deploy pipelines where
        #      a misconfigured DSN should fail fast and NOT silently fallback).
        missing_pg = bool(not raw_db_url)
        enforce_pg = str(os.environ.get('DB_ENFORCE_POSTGRES_PRODUCTION', '')).lower() in (
            '1', 'true', 'yes', 'on', 'require', 'strict'
        )
        if missing_pg:
            persistent_sqlite = (
                'sqlite:///' + os.path.join(inst_dir, 'glory2yahpub_prod_fallback.db')
            )
            if enforce_pg:
                raise ValueError(
                    "CRITICAL: DATABASE_URL not set in production and "
                    "DB_ENFORCE_POSTGRES_PRODUCTION=strict; refusing to start. "
                    "Set DATABASE_URL (Render → Environment → your PostgreSQL "
                    "managed instance connectionString)."
                )
            db_url = persistent_sqlite
            # Surface in logs AND in the app object so the bootstrap guard in
            # app/__init__.py can emit its ADS-PERSISTENCE CRITICAL warning
            # (SQLite is still OK here because the file is under /instance/).
            os.environ['G2Y_PG_FALLBACK_ACTIVE'] = '1'
            self.PRODUCTION_SQLITE_FALLBACK = True
        else:
            self.PRODUCTION_SQLITE_FALLBACK = False

        self.SQLALCHEMY_DATABASE_URI = db_url
        self.SQLALCHEMY_ENGINE_OPTIONS = _engine_options_for(db_url)

        # ----- Guards (prevent a broken/insecure production deploy) -----
        if not self.SECRET_KEY:
            raise ValueError("CRITICAL: SECRET_KEY must be set in production environment!")
        if not missing_pg and not _is_postgres_url(db_url):
            raise ValueError(
                "CRITICAL: DATABASE_URL was provided but is NOT a PostgreSQL "
                "connection string in production. Use a PostgreSQL DSN "
                "(postgresql://...). SQLite fallback is ONLY allowed when "
                "DATABASE_URL is completely unset (Render PG warm-up race)."
            )

        # ----- Session cookie security: Secure ON when behind HTTPS proxy (Render) -----
        _cse = os.environ.get('SESSION_COOKIE_SECURE', None)
        if _cse is not None:
            self.SESSION_COOKIE_SECURE = str(_cse) not in ('0', 'false', 'False', 'no', 'off')
        else:
            # Auto-detect PaaS HTTPS proxies (Render, Heroku-style $DYNO, generic $PORT)
            self.SESSION_COOKIE_SECURE = bool(
                os.environ.get('DYNO') or os.environ.get('RENDER') or os.environ.get('PORT')
            )
        # Remember-me cookies mirror session cookie security
        self.REMEMBER_COOKIE_SECURE = self.SESSION_COOKIE_SECURE
        self.REMEMBER_COOKIE_HTTPONLY = True
        self.REMEMBER_COOKIE_SAMESITE = 'Lax'

        # ----- Redis-override / no-Redis fallbacks (persistent session FS) -----
        if not self.REDIS_URL:
            self.CACHE_TYPE = 'simple'
            self.SESSION_TYPE = 'filesystem'
            self.SESSION_FILE_DIR = os.environ.get(
                'SESSION_FILE_DIR', os.path.join(inst_dir, '.flask_session')
            )
            try:
                os.makedirs(self.SESSION_FILE_DIR, exist_ok=True)
            except Exception:
                pass
            self.RATELIMIT_STORAGE_URL = 'memory://'


# Configuration dictionary — values are CLASSES; get_config() instantiates them.
config_dict = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'staging': StagingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig,
}


def get_config(env=None):
    """Get a CONFIG INSTANCE for the given (or detected) environment.

    IMPORTANT: returns an INSTANCE (not the class), so that __init__() runs
    and env vars are read FRESHLY at Flask startup. This fixes two bugs:
      1. ProductionConfig.__init__ SQLite guard + postgres:// → postgresql://
         URL translation were dead code (never executed before — Flask's
         from_object() only reads UPPERCASE class attrs on classes).
      2. UPLOAD_FOLDER / SESSION_FILE_DIR / LOG_DIR env overrides are picked
         up even when os.environ changes between process invocations.
    """
    if env is None:
        env = os.environ.get('FLASK_ENV', 'development')
    cls = config_dict.get(env, config_dict['default'])
    try:
        return cls()
    except TypeError:
        # If a subclass hasn't been updated and __init__ has unexpected
        # signature, fall back to instantiating without args — safety net.
        return cls.__new__(cls)
