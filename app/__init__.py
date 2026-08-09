"""
Glory2YahPub Application Factory
Modern Flask application with Redis caching and modular architecture
"""
import os
import logging
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect, CSRFError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_caching import Cache
from flask_socketio import SocketIO
from redis import Redis

# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address)
cache = Cache()
socketio = SocketIO()
redis_client = None


def create_app(config_name=None):
    """Application factory pattern"""
    
    # Create Flask app with correct paths
    app = Flask(__name__, 
                template_folder='../templates',
                static_folder='../static')
    
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')
    
    from app.config import get_config
    app.config.from_object(get_config(config_name))

    # Setup secret key - always comes from config
    secret_key = app.config.get("SECRET_KEY")
    if not secret_key:
        raise RuntimeError(
            "SECRET_KEY is required but was not found. "
            "Set the 'SECRET_KEY' environment variable or ensure .flask_secret_key file exists."
        )
    app.secret_key = secret_key

    setup_logging(app)
    
    # Initialize Redis with fallback mechanism
    global redis_client
    try:
        redis_url = app.config.get('REDIS_URL')
        if not redis_url or 'localhost' in redis_url:
            raise ConnectionError("No external Redis URL provided")
            
        redis_client = Redis.from_url(redis_url, decode_responses=True)
        redis_client.ping()
        app.logger.info('Redis connected successfully')
    except Exception as e:
        app.logger.error(f'Redis unavailable: {e}. Running in database-only mode.')
        redis_client = None
        # Fallback cache and limiter configs if Redis is down
        app.config['CACHE_TYPE'] = 'simple'
        app.config['RATELIMIT_STORAGE_URL'] = 'memory://'
    
    # Configure session settings explicitly before initializing extensions
    from datetime import timedelta
    # Ensure session cookies persist for 30 days even without "remember me"
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
    app.config['SESSION_REFRESH_EACH_REQUEST'] = True
    # Cookie settings for better persistence
    app.config['SESSION_COOKIE_NAME'] = 'glory2yah_session'
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    # Session cookie secure only if HTTPS in production, never in dev
    app.config['SESSION_COOKIE_SECURE'] = app.config.get('SESSION_COOKIE_SECURE', False)
    
    # Flask-Login remember cookie settings
    app.config['REMEMBER_COOKIE_NAME'] = 'glory2yah_remember'
    app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=365)  # 1 year remember
    app.config['REMEMBER_COOKIE_HTTPONLY'] = True
    app.config['REMEMBER_COOKIE_SAMESITE'] = 'Lax'
    app.config['REMEMBER_COOKIE_SECURE'] = app.config.get('SESSION_COOKIE_SECURE', False)
    app.config['REMEMBER_COOKIE_REFRESH_EACH_REQUEST'] = True

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    # Configure login_manager settings
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Ou dwe konekte pou aksede paj sa a.'
    # SESSION FIX: session_protection='strong' invalidates session on mobile IP/UA variations
    # (WiFi → 4G, browser minor updates) → user gets logged out randomly.
    # 'basic' only regenerates sid on login and doesn't invalidate on IP changes.
    login_manager.session_protection = 'basic'
    login_manager.needs_refresh_message = (u"Tanpri rekonfim modpas ou pou kontinye.")
    login_manager.needs_refresh_message_category = "info"

    # ===== PERSISTENT SESSION GLOBAL FIX — keep logged in until explicit logout =====
    #
    # Issue: flask-login session.permanent defaults to False → browser close = logout.
    # Requirement: session STAYS OPEN until user clicks logout (explicit action).
    # Fix: on every request, when a user IS authenticated, force session.permanent=True.
    # This also protects against routes forgetting to set permanent=True on login.
    # PERMANENT_SESSION_LIFETIME is already 30 days (line ~74).
    @app.before_request
    def _ensure_permanent_session_when_authenticated():
        from flask import session as _flask_sess
        try:
            from flask_login import current_user as _cu
            if _cu and _cu.is_authenticated:
                if not _flask_sess.get('_permanent'):
                    _flask_sess.permanent = True
        except Exception:
            # Never let session hooks break a request
            pass

    csrf.init_app(app)
    limiter.init_app(app)
    cache.init_app(app)

    # =====================================================================
    # RENDER PERSISTENCE — Transparent uploads serving fallback
    # (Pastes on every deploy previously wiped static/uploads/.)
    #
    # Problem:
    #   - 500+ template references use url_for('static', filename='uploads/X')
    #     or hardcoded /static/uploads/X URLs.
    #   - On Render, uploads are now saved to instance/uploads (persistent
    #     disk) instead of static/uploads (ephemeral container FS).
    #   - Flask static endpoint only serves static/ folder by default.
    #
    # Fix (ZERO template changes required):
    #   1. Register an explicit /uploads/<filename> endpoint that serves
    #      from app.config['UPLOAD_FOLDER'] (canonical: instance/uploads on
    #      Render, static/uploads locally).
    #   2. Add a WSGI-middleware-light before_request that INTERCEPTS any
    #      GET/HEAD for /static/uploads/<path>:
    #        a) If file exists in Flask's static/uploads → let Flask serve it.
    #        b) Else send from config.UPLOAD_FOLDER (persistent disk).
    #      This maintains 100% backward compatibility with every existing
    #      template URL without a single search/replace.
    # =====================================================================
    @app.route('/uploads/<path:filename>', methods=['GET', 'HEAD'])
    def _serve_upload_persistent(filename):
        import os as _os_up
        from flask import send_from_directory, abort as _abort_up, current_app as _cup
        safe_fn = _os_up.path.normpath(filename).lstrip('\\/')
        if safe_fn.startswith('..') or _os_up.path.isabs(safe_fn):
            _abort_up(404)
        return send_from_directory(_cup.config['UPLOAD_FOLDER'], safe_fn)

    @app.before_request
    def _static_uploads_fallback_to_persistent_disk():
        import os as _os_sb
        from flask import request as _req_sb, send_from_directory as _sfd, abort as _abt
        raw_path = _req_sb.path
        if _req_sb.method not in ('GET', 'HEAD'):
            return None
        prefixes = ('/static/uploads/', '/static\\uploads\\')
        match = None
        for p in prefixes:
            if raw_path.startswith(p):
                match = raw_path[len(p):]
                break
        if match is None:
            return None
        safe_match = _os_sb.path.normpath(match).lstrip('\\/')
        if safe_match.startswith('..') or _os_sb.path.isabs(safe_match):
            _abt(404)
        # First, try legacy static/uploads/ on the current filesystem
        static_root = app.static_folder or _os_sb.join(app.root_path, '..', 'static')
        legacy_path = _os_sb.join(static_root, 'uploads', safe_match)
        if _os_sb.isfile(legacy_path):
            return None  # Flask default static handler will take it
        # Fallback: persistent UPLOAD_FOLDER (instance/uploads/ on Render)
        persistent_dir = app.config.get('UPLOAD_FOLDER')
        if not persistent_dir:
            _abt(404)
        target = _os_sb.join(persistent_dir, safe_match)
        if not _os_sb.isfile(target):
            # Also check: if a dev locally has UPLOAD_FOLDER=instance/uploads
            # but an older ad's images referenced legacy static/uploads,
            # return 404 (consistent behaviour)
            _abt(404)
        return _sfd(persistent_dir, safe_match)

    # P1 FIX: Handle oversized uploads (100MB video promise in UI) with user-friendly
    # flash message instead of a generic "413 Request Entity Too Large".
    from werkzeug.exceptions import RequestEntityTooLarge as _RETL
    @app.errorhandler(_RETL)
    def _handle_entity_too_large(e):
        from flask import flash, redirect, request, url_for, render_template, current_app as _capp
        try:
            _capp.logger.warning(f"RequestEntityTooLarge: uri={request.path} size_hint={request.content_length}")
            flash('Fichye a twò gwo! Maksimòm otorize: 100 MB pou yon videyo. Tanpri redwi gwosè a epi reeseye.', 'error')
            ref = request.referrer or '/'
            if ref.startswith('/') or '://' in ref and request.host in ref:
                return redirect(ref)
            return redirect(url_for('main.submit_ad'))
        except Exception:
            return render_template('submit_ad.html'), 413

    # Initialize SocketIO with Redis if available — P1 FIX: restrict CORS origins, no wildcard
    import os as _os
    _allowed_origins_env = _os.environ.get('SOCKETIO_CORS_ALLOWED_ORIGINS')
    if _allowed_origins_env:
        _cors_origins = [o.strip() for o in _allowed_origins_env.split(',') if o.strip()]
    elif config_name == 'production':
        _cors_origins = []
    else:
        _cors_origins = "*"
    if redis_client:
        socketio.init_app(app, cors_allowed_origins=_cors_origins, message_queue=app.config['REDIS_URL'])
    else:
        socketio.init_app(app, cors_allowed_origins=_cors_origins)
        app.logger.warning('SocketIO running without Redis message queue')
    
    # Custom template filter to get video embed URL (autoplay on viewport)
    # Handles YouTube (watch/shorts/embed/youtu.be/m.youtube), Vimeo, TikTok,
    # Instagram (reels/p/tv), Facebook Watch/Video.
    # All returned embeds include ?autoplay=1&mute=1&playsinline=1&loop=1 so the
    # browser autoplay policy allows silent-in-viewport playback (cross-origin
    # iframes will NOT start unless the src explicitly opts-in + muted).
    @app.template_filter('get_embed_url')
    def get_embed_url(url):
        import re, urllib.parse as _urlp
        if not url:
            return None
        s = str(url).strip()
        if not s:
            return None

        # ----- YouTube (watch/shorts/embed/youtu.be/live/m.youtube/yt music) -----
        yt_re = (
            r'(?:(?:https?:)?//)?'
            r'(?:www\.|m\.|music\.)?'
            r'(?:youtube(?:-nocookie)?\.com/'
            r'(?:watch\?(?:.*?&)?v=|shorts/|embed/|live/|v/)'
            r'|youtu\.be/)'
            r'([A-Za-z0-9_-]{11})'
        )
        m = re.search(yt_re, s)
        if m:
            vid = m.group(1)
            params = {
                'autoplay': '1', 'mute': '1', 'playsinline': '1',
                'rel': '0', 'enablejsapi': '1', 'modestbranding': '1',
                'loop': '1', 'playlist': vid,
                'origin': '', 'widget_referrer': '', 'hl': 'ht', 'cc_lang_pref': 'ht'
            }
            qs = _urlp.urlencode(params, safe='', quote_via=_urlp.quote)
            return f'https://www.youtube-nocookie.com/embed/{vid}?{qs}'

        # ----- Vimeo -----
        vm_re = r'(?:https?:)?//(?:www\.)?vimeo\.com/(?:video/)?(\d+)'
        m = re.search(vm_re, s)
        if m:
            vid = m.group(1)
            params = {
                'autoplay': '1', 'muted': '1', 'playsinline': '1',
                'loop': '1', 'title': '0', 'byline': '0', 'portrait': '0',
                'speed': '0', 'transparent': '0', 'background': '0'
            }
            qs = _urlp.urlencode(params)
            return f'https://player.vimeo.com/video/{vid}?{qs}'

        # ----- TikTok (www.tiktok.com/@user/video/ID OR vm.tiktok.com/SHORT) -----
        tt_re = (
            r'(?:https?:)?//(?:www\.)?tiktok\.com/'
            r'(?:@[\w.]+/video|v)/([0-9A-Za-z]{8,25})'
        )
        m = re.search(tt_re, s)
        if not m:
            tt_short = r'(?:https?:)?//vm\.tiktok\.com/([A-Za-z0-9]{3,16})'
            ms = re.search(tt_short, s)
            if ms:
                # TikTok short links redirect to full /video/<id> URL; use the
                # canonical TikTok embed by short code + autoplay params.
                sc = ms.group(1)
                params = {'autoplay': '1', 'muted': 'true', 'playsinline': '1',
                          'loop': '1', 'controls': '1', 'enablejsapi': '1'}
                qs = _urlp.urlencode(params)
                return f'https://www.tiktok.com/embed/v2/{sc}?{qs}'
        if m:
            vid = m.group(1)
            params = {'autoplay': '1', 'muted': 'true', 'playsinline': '1',
                      'loop': '1', 'controls': '1', 'enablejsapi': '1'}
            qs = _urlp.urlencode(params)
            return f'https://www.tiktok.com/embed/v2/{vid}?{qs}'

        # ----- Instagram: reels/ p/ tv/ -----
        ig_re = (
            r'(?:https?:)?//(?:www\.)?instagram\.com/'
            r'(reel|reels|p|tv)/([A-Za-z0-9_-]{5,})'
        )
        m = re.search(ig_re, s)
        if m:
            kind = m.group(1)
            code = m.group(2)
            # Instagram embed: autoplay=1 + muted via ?v=2 on /embed/
            return f'https://www.instagram.com/{kind}/{code}/embed/?autoplay=1&mute=1&loop=1&playsinline=1&v=2'

        # ----- Facebook / Meta: watch/ video.php?v= groups/ share/ -----
        fb_re = (
            r'(?:https?:)?//(?:www\.|m\.|business\.)?'
            r'(?:facebook|fb)\.com/'
            r'(?:watch/?\?v=|video\.php\?v=|'
            r'(?:[\w.%-]+/)?videos/|groups/[\w.%-]+/posts/|share/[vr]/|reel/|'
            r'story\.php\?story_fbid=)'
            r'(\d{5,})'
        )
        m = re.search(fb_re, s)
        if m:
            vid = m.group(1)
            fb_src = _urlp.quote(s, safe='')
            params = {
                'href': fb_src, 'show_captions': 'false',
                'allowfullscreen': 'true', 'autoplay': '1', 'mute': '1',
                'playsinline': '1', 'loop': '1'
            }
            qs = _urlp.urlencode(params)
            return f'https://www.facebook.com/plugins/video.php?{qs}'

        return None
    
    @login_manager.user_loader
    def load_user(user_id):
        from app.models.user import User
        try:
            user_id_int = int(user_id)
            # P2 FIX: replace deprecated legacy User.query.get() with modern db.session.get()
            user = db.session.get(User, user_id_int)
            if user and user.is_active:
                return user
            return None
        except (ValueError, TypeError, Exception):
            return None
    
    @app.context_processor
    def inject_global_data():
        from flask_login import current_user
        from app.services.cart_service import CartService
        from app.services.gkach_service import GkachService # Import GkachService
        
        data = {
            'is_logged_in': current_user.is_authenticated,
            'cart_count': 0,
            'gkach_balance': 0 # Default to 0
        }
        
        if current_user.is_authenticated:
            try:
                cart_totals = CartService.calculate_totals(current_user.id)
                data['cart_count'] = cart_totals['count']
                data['gkach_balance'] = GkachService.get_balance(current_user.whatsapp) # Get Gkach balance
            except Exception as e:
                app.logger.error(f"Error injecting global data: {e}")
                pass
                
        return data

    register_blueprints(app)
    register_error_handlers(app)
    register_template_filters(app)
    
    # Import all models first to resolve relationships
    with app.app_context():
        from app.models.user import User
        from app.models.user_gkach import UserGkach
        from app.models.ad import Ad
        from app.models.delivery import Delivery
        from app.models.delivery_item import DeliveryItem
        from app.models.batch import Batch
        from app.models.batch_click import BatchClick
        from app.models.batch_ad import BatchAd
        from app.models.gkach_transaction import GkachTransaction
        from app.models.cart import CartItem
        from app.models.message import Message
        from app.models.ad_interactions import AdLike, AdStar, AdComment, AdRating
        from app.models.admin_settings import AdminSettings # Import AdminSettings
        from app.models.party import Party, PartyParticipant
        from app.models.konferans import KonferansRoom, KonferansRecording
        from app.models.mennem_trip import MennemTrip
        try:
            from app.models.app_installation import AppInstallation  # PWA tracking model
        except ImportError:
            app.logger.warning('AppInstallation model not available - import skipped')
            AppInstallation = None
        # Import ecole_biblique models so their tables get created
        from ecole_biblique.models import EcoleUser, Course, EcoleStudent, Grade, AdmissionTest, AdmissionAnswer, Module, StudentModule, Payment, TermsAcceptance, AuditLog
        # Import charity models
        from app.models.charity import CharityDonation, CharityCause
        # Import bank models
        from app.models.bank import LoanProduct, Loan, LoanRepayment, InvestmentProduct, Investment
        db.create_all()
        
        # =====================================================================
        # BATCH_CLICKS MIGRATION: add `clicker_ip` column if missing (anti-fraud
        # per-IP limit on ad-batch sharing clicks). SQLAlchemy create_all() does
        # NOT alter existing tables, so this idempotent patch inspects the live
        # schema and ALTERs only when the column is absent.
        # =====================================================================
        try:
            from sqlalchemy import inspect as _sa_inspect2
            from sqlalchemy import text as _sa_text2
            _insp2 = _sa_inspect2(db.engine)
            if _insp2.has_table('batch_clicks'):
                _bc_cols = {c['name'] for c in _insp2.get_columns('batch_clicks')}
                if 'clicker_ip' not in _bc_cols:
                    db.session.execute(_sa_text2('ALTER TABLE batch_clicks ADD COLUMN clicker_ip VARCHAR(45)'))
                    db.session.commit()
                    app.logger.info('BATCH_CLICKS MIGRATION: added batch_clicks.clicker_ip column')
                if 'clicker_device' not in _bc_cols:
                    try:
                        db.session.execute(_sa_text2('ALTER TABLE batch_clicks ADD COLUMN clicker_device VARCHAR(64)'))
                    except Exception:
                        db.session.rollback()
                        db.session.execute(_sa_text2('ALTER TABLE batch_clicks ADD COLUMN clicker_device VARCHAR(64) DEFAULT NULL'))
                    db.session.commit()
                    app.logger.info('BATCH_CLICKS MIGRATION: added batch_clicks.clicker_device column')
        except Exception as _e2:
            db.session.rollback()
            app.logger.warning(f"BATCH_CLICKS MIGRATION: could not add clicker_ip column: {_e2}")

        # =====================================================================
        # ADS MIGRATION: add `category` column to existing `ads` table.
        # SQLAlchemy create_all() does NOT alter existing tables — on databases
        # created before the category column existed, queries filter_by(category=..)
        # would raise "no such column: ads.category". This idempotent patch
        # inspects the live schema and ALTERs only if the column is missing.
        # =====================================================================
        try:
            from sqlalchemy import inspect as _sa_inspect
            from sqlalchemy import text as _sa_text
            _insp = _sa_inspect(db.engine)
            _ads_cols = {c['name'] for c in _insp.get_columns('ads')} if _insp.has_table('ads') else set()
            if 'category' not in _ads_cols:
                db.session.execute(_sa_text('ALTER TABLE ads ADD COLUMN category VARCHAR(50) DEFAULT "other"'))
                db.session.commit()
                app.logger.info('ADS MIGRATION: added ads.category column (default "other")')
            if 'quantity' not in _ads_cols:
                db.session.execute(_sa_text('ALTER TABLE ads ADD COLUMN quantity INTEGER DEFAULT 1'))
                db.session.commit()
                app.logger.info('ADS MIGRATION: added ads.quantity column (default 1)')
            if 'publish_fee_gkach' not in _ads_cols:
                db.session.execute(_sa_text('ALTER TABLE ads ADD COLUMN publish_fee_gkach INTEGER DEFAULT 1000'))
                db.session.commit()
                app.logger.info('ADS MIGRATION: added ads.publish_fee_gkach column (default 1000)')
        except Exception as _e:
            db.session.rollback()
            app.logger.warning(f"ADS MIGRATION: could not add ads columns: {_e}")

        # =====================================================================
        # SOFT DELETE MIGRATION: add `deleted_at` column to all existing tables
        # that inherit from BaseModel. db.create_all() does NOT alter existing
        # tables, so on databases created before the deleted_at column existed,
        # queries would raise "no such column: <table>.deleted_at".
        # This idempotent patch inspects the live schema and ALTERs only when
        # the column is missing (Audit #19 - soft deletes).
        # =====================================================================
        try:
            from sqlalchemy import inspect as _sa_inspect_sd
            from sqlalchemy import text as _sa_text_sd
            from app.models.base import BaseModel as _BaseM
            _insp_sd = _sa_inspect_sd(db.engine)
            _sd_models = [_BaseM.__subclasses__()]
            _sd_tables_checked = 0
            _sd_tables_altered = 0
            for _sd_cls_list in _sd_models:
                for _sd_cls in _sd_cls_list:
                    try:
                        _sd_tbl = _sd_cls.__table__
                        _sd_tbl_name = _sd_tbl.name
                        if not _insp_sd.has_table(_sd_tbl_name):
                            continue
                        _sd_cols = {c['name'] for c in _insp_sd.get_columns(_sd_tbl_name)}
                        if 'deleted_at' not in _sd_cols:
                            db.session.execute(_sa_text_sd(f'ALTER TABLE {_sd_tbl_name} ADD COLUMN deleted_at DATETIME'))
                            db.session.commit()
                            app.logger.info(f'SOFT DELETE MIGRATION: added {_sd_tbl_name}.deleted_at column')
                            _sd_tables_altered += 1
                        _sd_tables_checked += 1
                    except Exception as _sd_e:
                        db.session.rollback()
                        app.logger.warning(f'SOFT DELETE MIGRATION: could not add deleted_at to table: {_sd_e}')
            app.logger.info(f'SOFT DELETE MIGRATION: checked {_sd_tables_checked} tables, altered {_sd_tables_altered}')
        except Exception as _sd_exc:
            db.session.rollback()
            app.logger.warning(f'SOFT DELETE MIGRATION: could not run: {_sd_exc}')
        
        # Create default loan products if they don't exist
        try:
            default_loan_products = [
                {'name': 'Prè Pèsonèl', 'description': 'Prè pou bezwen pèsonèl', 'min_amount': 100, 'max_amount': 5000, 'interest_rate': 5.0, 'duration_days': 30},
                {'name': 'Prè Biznis', 'description': 'Prè pou ti biznis', 'min_amount': 500, 'max_amount': 20000, 'interest_rate': 7.0, 'duration_days': 90},
                {'name': 'Prè Edikasyon', 'description': 'Prè pou edikasyon', 'min_amount': 200, 'max_amount': 10000, 'interest_rate': 3.0, 'duration_days': 60},
            ]
            for product_data in default_loan_products:
                existing = LoanProduct.query.filter_by(name=product_data['name']).first()
                if not existing:
                    product = LoanProduct(**product_data)
                    db.session.add(product)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            app.logger.warning(f"Could not create default loan products: {e}")
        
        # Create default investment products if they don't exist
        try:
            default_investment_products = [
                {'name': 'Envestisman Kout Tèm', 'description': 'Envestisman pou 30 jou', 'min_amount': 100, 'max_amount': 5000, 'interest_rate': 5.0, 'duration_days': 30, 'early_withdrawal_penalty': 10.0},
                {'name': 'Envestisman Mwayen Tèm', 'description': 'Envestisman pou 90 jou', 'min_amount': 500, 'max_amount': 20000, 'interest_rate': 8.0, 'duration_days': 90, 'early_withdrawal_penalty': 8.0},
                {'name': 'Envestisman Long Tèm', 'description': 'Envestisman pou 180 jou', 'min_amount': 1000, 'max_amount': 50000, 'interest_rate': 12.0, 'duration_days': 180, 'early_withdrawal_penalty': 5.0},
            ]
            for product_data in default_investment_products:
                existing = InvestmentProduct.query.filter_by(name=product_data['name']).first()
                if not existing:
                    product = InvestmentProduct(**product_data)
                    db.session.add(product)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            app.logger.warning(f"Could not create default investment products: {e}")
        
        # =====================================================================
        # ADS CACHE INVALIDATION AT STARTUP
        # Redis persists between deploys. On Render, a new deploy reuses the
        # same Redis. If an admin approved ads just before a deploy, the cached
        # `ads:approved` list would still hold the OLD data (10-min TTL) and the
        # freshly-approved ads would appear "disappeared" after the commit.
        # Fix: invalidate ALL ad caches on every startup so the DB is the
        # single source of truth right after boot.
        # =====================================================================
        try:
            from app.services.ad_service import AdService
            AdService.invalidate_all_ad_caches()
            app.logger.info('ADS CACHE: invalidated approved-ads + ad:* caches at startup')
        except Exception as _e_adcache:
            app.logger.warning(f'ADS CACHE: startup invalidation skipped: {_e_adcache}')

        # Create default charity causes if they don't exist
        try:
            default_causes = [
                {'cause_id': 'education', 'name': 'Edikasyon', 'description': 'Sipò pou edikasyon timoun ki nan bezwen', 'icon': '📚'},
                {'cause_id': 'health', 'name': 'Sante', 'description': 'Sipò medikal pou moun ki malad', 'icon': '🏥'},
                {'cause_id': 'community', 'name': 'Kominote', 'description': 'Pwojè kominotè ak devlopman lokal', 'icon': '🏘️'},
                {'cause_id': 'food', 'name': 'Manje', 'description': 'Distribisyon manje pou moun ki grangou', 'icon': '🍲'},
                {'cause_id': 'general', 'name': 'Jeneral', 'description': 'Don jeneral pou tout bezwen charitab', 'icon': '❤️'},
            ]
            for cause_data in default_causes:
                existing = CharityCause.query.filter_by(cause_id=cause_data['cause_id']).first()
                if not existing:
                    import uuid
                    cause = CharityCause(
                        cause_id=cause_data['cause_id'],
                        name=cause_data['name'],
                        description=cause_data['description'],
                        icon=cause_data['icon'],
                        is_active=True
                    )
                    db.session.add(cause)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            app.logger.warning(f"Could not create default charity causes: {e}")
        
        # =====================================================================
        # Admin user bootstrap — IDEMPOTENT (cf pattern StanD ci-dessous):
        #   - Pseudo/WhatsApp par défaut: pseudo="Admin509" whatsapp="+50942882076"
        #     (User feedback: connexion par pseudo Admin509 attendue, pas le numéro.)
        #   - Password par défaut: "StanGlory2YahPub1986"
        #   - Sécurité: JAMAIS en PROD le MDP par défaut n'est créé si
        #     ADMIN_PASSWORD est setté dans .env (override).
        #   - Idempotent: si le compte existe déjà par whatsapp ou pseudo
        #     (même créé à la main), on force is_admin=True, is_active=True,
        #     on met à jour pseudo/admin_pseudo ET on réécrit toujours le
        #     password_hash (sécurité: synchro garantie avec la config).
        # =====================================================================
        try:
            admin_phone    = _os.environ.get('ADMIN_WHATSAPP', '+50942882076')
            admin_password = _os.environ.get('ADMIN_PASSWORD', 'StanGlory2YahPub1986')
            admin_pseudo   = _os.environ.get('ADMIN_PSEUDO',   'Admin509')
            admin_name     = _os.environ.get('ADMIN_NAME',     'Glory2YahPub')
            admin_user = None
            # Recherche : d'abord par pseudo (Admin509 — cas nominal),
            # ensuite par whatsapp (compatibilité legacy), puis n'importe quel admin existant.
            if admin_pseudo:
                admin_user = User.query.filter(User.pseudo.ilike(admin_pseudo)).first()
            if (not admin_user) and admin_phone:
                admin_user = User.query.filter_by(whatsapp=admin_phone).first()
            if not admin_user:
                any_admin = User.query.filter_by(is_admin=True).first()
                if any_admin:
                    admin_user = any_admin
            if not admin_user:
                # Aucun admin du tout → CREATE
                if not (admin_phone and admin_password):
                    app.logger.warning(
                        "Aucun administrateur existant. Définissez ADMIN_WHATSAPP + ADMIN_PASSWORD dans .env pour créer le compte admin initial."
                    )
                else:
                    admin_user = User(
                        whatsapp=admin_phone,
                        pseudo=admin_pseudo,
                        name=admin_name,
                        auth_provider='whatsapp',
                        is_active=True,
                        is_admin=True
                    )
                    admin_user.set_password(admin_password)
                    db.session.add(admin_user)
                    db.session.flush()
                    admin_gkach = UserGkach.query.filter_by(user_whatsapp=admin_user.whatsapp).first()
                    if not admin_gkach:
                        db.session.add(UserGkach(user_id=admin_user.id, user_whatsapp=admin_user.whatsapp, gkach_balance=0))
                    db.session.commit()
                    app.logger.info(
                        f"Admin user CREATED: pseudo={admin_pseudo!r} whatsapp={admin_phone!r} "
                        f"password={'<from env ADMIN_PASSWORD>' if _os.environ.get('ADMIN_PASSWORD') else 'default StanGlory2YahPub1986 (DEV/DEMO only)'}"
                    )
            else:
                # Admin existe → UPGRADE IDEMPOTENT (synchronise champs)
                changed = False
                if admin_user.is_admin is not True:
                    admin_user.is_admin = True
                    changed = True
                if admin_user.is_active is not True:
                    admin_user.is_active = True
                    changed = True
                if admin_phone and (admin_user.whatsapp != admin_phone):
                    admin_user.whatsapp = admin_phone
                    changed = True
                if admin_pseudo and (admin_user.pseudo != admin_pseudo):
                    admin_user.pseudo = admin_pseudo
                    changed = True
                if admin_name and (admin_user.name != admin_name):
                    admin_user.name = admin_name
                    changed = True
                # Password: toujours sync pour garantir user request "StanGlory2YahPub1986"
                # (set_password idempotent au niveau UX, rien ne change si même MDP)
                if admin_password:
                    admin_user.set_password(admin_password)
                    changed = True
                if admin_user.auth_provider != 'whatsapp':
                    admin_user.auth_provider = 'whatsapp'
                    changed = True
                if changed:
                    # Si UserGkach row manque (migrations anciennes), créé
                    g = UserGkach.query.filter(
                        (UserGkach.user_id == admin_user.id) |
                        (UserGkach.user_whatsapp == admin_user.whatsapp)
                    ).first()
                    if not g:
                        db.session.add(UserGkach(user_id=admin_user.id, user_whatsapp=admin_user.whatsapp, gkach_balance=0))
                    db.session.commit()
                    app.logger.info(
                        f"Admin user IDEMPOTENT UPGRADED: pseudo={admin_user.pseudo!r} "
                        f"whatsapp={admin_user.whatsapp!r} is_admin={admin_user.is_admin} pw_sync=OK"
                    )
        except Exception as e:
            app.logger.warning(f"Could not process admin user setup: {e}")
            db.session.rollback()

        # Test user — P1 FIX: ONLY when FLASK_ENV=development AND TEST_USER=1 env var set; NEVER in production
        try:
            import os as __os
            if config_name != 'production' and __os.environ.get('CREATE_TEST_USER', '0') == '1':
                test_phone = '+50912345678'
                test_user = User.query.filter_by(whatsapp=test_phone).first()
                if not test_user:
                    pseudo = 'testuser'
                    count = 1
                    while User.query.filter_by(pseudo=pseudo).first():
                        pseudo = f'testuser{count}'
                        count += 1
                    test_pw = __os.environ.get('TEST_USER_PASSWORD', None)
                    if not test_pw:
                        test_pw = '123456'
                    test_user = User(
                        whatsapp=test_phone,
                        pseudo=pseudo,
                        name='Test User',
                        auth_provider='whatsapp',
                        is_active=True
                    )
                    test_user.set_password(test_pw)
                    db.session.add(test_user)
                    db.session.flush()
                    test_gkach = UserGkach.query.filter_by(user_whatsapp=test_user.whatsapp).first()
                    if not test_gkach:
                        test_gkach = UserGkach(
                            user_id=test_user.id,
                            user_whatsapp=test_user.whatsapp,
                            gkach_balance=1000
                        )
                        db.session.add(test_gkach)
                    db.session.commit()
                    app.logger.info(f"Test user created (dev, opt-in): +50912345678 / CREATE_TEST_USER=1")
        except Exception as e:
            app.logger.warning(f"Could not create test user (opt-in): {e}")
            db.session.rollback()

        # =================================================================
        # DEFECT #6 FIX: Demo account that matches the YELLOW HINT shown on
        # /auth/login ("Modpas ka: 123456 oswa pass123" + "Pseudo demo: StanD").
        # Without this, users follow the UI hint → type "StanD / pass123" →
        # account doesn't exist → FAIL → red borders (image ③) — infinite loop.
        # Behaviour:
        #  - NEVER run on production Render (safety gate: config_name != production)
        #    OR: override by env FORCE_CREATE_STAND_DEMO=1 (for non-prod debugging)
        #  - Idempotent: if StanD pseudo already exists, DO NOT overwrite existing
        #    password (may have been changed by owner); only ensure is_active=True
        #    and if password is NOT set (broken account), set default to pass123.
        # =================================================================
        try:
            import os as __os_stand
            _force = (__os_stand.environ.get('FORCE_CREATE_STAND_DEMO', '0') == '1')
            _prod_ok = (config_name != 'production') or _force
            if _prod_ok:
                _pseudo = 'StanD'
                _default_pw = 'pass123'
                _whatsapp = __os_stand.environ.get(
                    'STAND_WHATSAPP', '+50948592888'
                )
                u = User.query.filter(User.pseudo.ilike(_pseudo)).first()
                if not u:
                    u = User.query.filter_by(whatsapp=_whatsapp).first()
                if not u:
                    u = User(
                        whatsapp=_whatsapp,
                        pseudo=_pseudo,
                        name='StanD (Demo)',
                        auth_provider='password',
                        is_active=True,
                        is_admin=False,
                    )
                    u.set_password(_default_pw)
                    db.session.add(u)
                    db.session.flush()
                    try:
                        from app.models.user_gkach import UserGkach as _UG
                        if not _UG.query.filter_by(user_whatsapp=u.whatsapp).first():
                            db.session.add(_UG(user_id=u.id, user_whatsapp=u.whatsapp, gkach_balance=0))
                    except Exception:
                        pass
                    db.session.commit()
                    app.logger.info(
                        'Created demo login account pseudo=%s (password="%s") to match UI hint.',
                        _pseudo, _default_pw,
                    )
                else:
                    changed = False
                    if not u.is_active:
                        u.is_active = True
                        changed = True
                    _no_pw = (not getattr(u, 'password_hash', None))
                    need_pw_reset = False
                    try:
                        from werkzeug.security import check_password_hash as _cph
                        if _no_pw:
                            need_pw_reset = True
                    except Exception:
                        if _no_pw:
                            need_pw_reset = True
                    if need_pw_reset:
                        u.set_password(_default_pw)
                        changed = True
                    # ----------------------------------------------------------
                    # ADS LOADING FIX (validate_whatsapp corrupted prefix):
                    # If StanD exists from OLDER buggy bootstrap with a garbage
                    # whatsapp like "+509STAN" (letters + digits), the old
                    # validator silently stripped letters → "+509" country-only,
                    # causing all Ad.user_whatsapp for this user to be stored
                    # under wrong identity → "can't load my ADS".
                    # Strict fix (>=7 numeric digits): replace with clean
                    # _whatsapp = +15557826391 (or env STAND_WHATSAPP).
                    # ----------------------------------------------------------
                    import re as __re_stand
                    _digits = __re_stand.sub(r'\D', '', u.whatsapp or '')
                    _invalid_len = (len(_digits) < 7)
                    _has_letters = bool(__re_stand.search(r'[A-Za-z]', u.whatsapp or ''))
                    if _invalid_len or _has_letters:
                        app.logger.info(
                            'StanD repair: CORRUPTED whatsapp=%r (digits=%d letters=%s) '
                            '→ upgrading to %r (identity-safe for ADS / Gkach rows).',
                            u.whatsapp, len(_digits), _has_letters, _whatsapp,
                        )
                        old_whatsapp = u.whatsapp
                        u.whatsapp = _whatsapp
                        changed = True
                        # Cascade: UserGkach.user_whatsapp must keep balance.
                        try:
                            from app.models.user_gkach import UserGkach as _UG2
                            ug = _UG2.query.filter_by(user_id=u.id).first()
                            if ug:
                                ug.user_whatsapp = _whatsapp
                                app.logger.info(
                                    '  → UserGkach.user_whatsapp also updated (balance preserved).',
                                )
                        except Exception as _ug_err:
                            app.logger.warning('  → UserGkach cascade skipped: %s', _ug_err)
                        # NOTE: orphan Ad rows stored under old corrupted
                        # user_whatsapp (e.g. "+509") cannot be safely re-mapped
                        # because the old validator destroyed identity info.
                        # New ads will be stored under the NEW clean value.
                    if changed:
                        db.session.commit()
                        app.logger.info(
                            'Demo login account pseudo=%s repaired (is_active / password / whatsapp set).',
                            _pseudo,
                        )
        except Exception as _e:
            app.logger.warning(f'StanD demo-account bootstrap skipped: {_e}')
            try:
                db.session.rollback()
            except Exception:
                pass

        # =====================================================================
        # GLOBAL "ALL USERS" WhatsApp integrity repair (for ADS loading).
        # Runs AFTER the specific Admin / StanD blocks (which handle known
        # identities). Purpose: catch any other legacy user whose `whatsapp`
        # column was corrupted by the OLD buggy validate_whatsapp which
        # silently stripped letters (e.g. "+509CHARITY" → "+509"), causing
        #   AdService.get_user_ads(current_user.whatsapp) → EMPTY or WRONG rows
        # because the WHERE clause uses an identity NOT associated with their rows.
        # Idempotent (safe to re-run every startup):
        #   - Skip rows that already pass the strict validator guard (>=7 digits
        #     and zero letters) — no-op for clean users.
        #   - Repair target: deterministic pseudo-phone "+509" + (10_000_000+id)
        #     → unique per user, 11 digits (passes E.164 validator guard).
        #   - Cascade to UserGkach.user_whatsapp (balance preserved).
        #   - Cascade to Ad.user_whatsapp (moves ALL ads under the old corrupted
        #     phone back to the new deterministic phone; preserves ownership).
        #   - NEVER overwrites a non-empty password_hash on real accounts (security).
        # =====================================================================
        try:
            import re as __re_all_wa
            def __safe_repair_whatsapp(uid):
                return "+509" + str(10_000_000 + int(uid))
            _any_global = False
            for _u in User.query.order_by(User.id.asc()).all():
                _raw = _u.whatsapp or ''
                _d = __re_all_wa.sub(r'\D', '', _raw)
                _L = bool(__re_all_wa.search(r'[A-Za-z]', _raw))
                _bad = (len(_d) < 7) or _L
                if not _bad:
                    continue
                _old = _u.whatsapp
                _new = __safe_repair_whatsapp(_u.id)
                app.logger.info(
                    'User whatsapp repair #%d pseudo=%r %r -> %r '
                    '(digits=%d letters=%s — identity-safe for ADS loading).',
                    _u.id, _u.pseudo, _old, _new, len(_d), _L,
                )
                _u.whatsapp = _new
                try:
                    from app.models.user_gkach import UserGkach as _UG3
                    ug = _UG3.query.filter_by(user_id=_u.id).first()
                    if ug is None:
                        db.session.add(_UG3(user_id=_u.id, user_whatsapp=_new, gkach_balance=0))
                        app.logger.info('  → created missing UserGkach row (balance=0).')
                    elif ug.user_whatsapp != _new:
                        ug.user_whatsapp = _new
                        app.logger.info('  → UserGkach.user_whatsapp fixed (balance %d preserved).', ug.gkach_balance)
                except Exception as _x:
                    app.logger.warning('  → UserGkach cascade skipped: %s', _x)
                try:
                    from app.models.ad import Ad as _A
                    if _old:
                        _mv = _A.query.filter_by(user_whatsapp=_old).update(
                            {_A.user_whatsapp: _new}, synchronize_session='fetch'
                        )
                        if _mv:
                            app.logger.info('  → Ad rows moved (old %r → new %r): %d rows.', _old, _new, _mv)
                except Exception as _x:
                    app.logger.warning('  → Ad cascade skipped: %s', _x)
                _any_global = True
            if _any_global:
                db.session.commit()
                app.logger.info('Global user-whatsapp integrity repair complete (committed).')
        except Exception as _e:
            app.logger.warning(f'Global user-whatsapp integrity repair skipped: {_e}')
            try: db.session.rollback()
            except Exception: pass

        # =====================================================================
        # Bank blueprints seed: default LoanProducts + InvestmentProducts.
        # Idempotent: skip if ANY existing rows for that table.
        # (Admin can edit / deactivate them later from /bank/admin)
        # =====================================================================
        try:
            from app.models.bank import (
                LoanProduct as _LP,
                InvestmentProduct as _IP,
            )
            # ---- Loans (2 defaults) ----
            if _LP.query.count() == 0:
                _lp_defaults = [
                    _LP(
                        name='Prè Kout Tèm (Express)',
                        description='Prè kout tèm pou biznis oswa bezwen imedya. 5%/an, rann nan 30 jou.',
                        min_amount=500, max_amount=50000,
                        interest_rate=5.0, duration_days=30, is_active=True,
                    ),
                    _LP(
                        name='Prè Konsomatè (Long)',
                        description='Prè konsomatè plis gwo montan. 12%/an, rann nan 180 jou (6 mwa).',
                        min_amount=10000, max_amount=500000,
                        interest_rate=12.0, duration_days=180, is_active=True,
                    ),
                ]
                db.session.add_all(_lp_defaults)
                db.session.commit()
                app.logger.info(f'Bank: CREATED {len(_lp_defaults)} default LoanProducts')
            else:
                app.logger.info(f'Bank: skipped LoanProduct seed ({_LP.query.count()} existing rows)')

            # ---- Investments (2 defaults) ----
            if _IP.query.count() == 0:
                _ip_defaults = [
                    _IP(
                        name='Epargne Klasik 90 jou',
                        description='Envestisman ki gen 8%/an. Matirite 3 mwa. Penalite retrè bonè: 10%.',
                        min_amount=1000, max_amount=500000,
                        interest_rate=8.0, duration_days=90,
                        early_withdrawal_penalty=10.0, is_active=True,
                    ),
                    _IP(
                        name='Envestisman Long 12 mwa',
                        description='Envestisman long tèm: 15%/an, matirite 365 jou. Penalite retrè bonè: 20%.',
                        min_amount=50000, max_amount=None,
                        interest_rate=15.0, duration_days=365,
                        early_withdrawal_penalty=20.0, is_active=True,
                    ),
                ]
                db.session.add_all(_ip_defaults)
                db.session.commit()
                app.logger.info(f'Bank: CREATED {len(_ip_defaults)} default InvestmentProducts')
            else:
                app.logger.info(f'Bank: skipped InvestmentProduct seed ({_IP.query.count()} existing rows)')
        except Exception as _e:
            app.logger.warning(f'Bank products seed skipped: {type(_e).__name__}: {_e}')
            try:
                db.session.rollback()
            except Exception:
                pass

    app.logger.info(f'Glory2YahPub started in {config_name} mode')

    return app


def register_blueprints(app):
    """Register all blueprints"""
    from app.routes.main import main_bp
    from app.routes.auth import auth_bp
    from app.routes.marketplace import marketplace_bp
    from app.routes.cart import cart_bp
    from app.routes.delivery import delivery_bp
    from app.routes.gkach import gkach_bp
    from app.routes.admin import admin_bp
    from app.routes.share import share_bp
    
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(marketplace_bp)  # Already has /mache prefix
    app.register_blueprint(cart_bp, url_prefix='/cart')
    app.register_blueprint(delivery_bp, url_prefix='/delivery')
    app.register_blueprint(gkach_bp, url_prefix='/gkach')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(share_bp, url_prefix='/s')
    
    # Register PWA blueprint
    try:
        from app.routes.pwa import pwa_bp
        app.register_blueprint(pwa_bp)
        app.logger.info('Registered PWA blueprint at /pwa')
    except Exception as e:
        app.logger.warning(f"Could not register PWA blueprint: {e}")
        pass
    
    # Register old blueprints
    try:
        from konferans.routes import konferans_bp, register_socketio_handlers
        app.register_blueprint(konferans_bp)
        register_socketio_handlers(socketio)
    except:
        pass
    
    try:
        from ecole_biblique.app import ecole_biblique_bp
        app.register_blueprint(ecole_biblique_bp, url_prefix='/ecole_biblique')
        app.logger.info("Registered ecole_biblique blueprint at /ecole_biblique")
    except Exception as e:
        app.logger.warning(f"Could not register ecole_biblique: {e}")
        pass
    
    try:
        from party.app import party_bp
        app.register_blueprint(party_bp, url_prefix='/fet')
    except:
        pass
    
    try:
        from mennem.app import mennem_bp
        app.register_blueprint(mennem_bp, url_prefix='/mennenm')
        app.logger.info("Successfully registered mennem_bp at /mennenm")
    except Exception as e:
        app.logger.error(f"Failed to register mennem_bp: {type(e).__name__}: {str(e)}")
        import traceback
        app.logger.error(traceback.format_exc())
    
    try:
        from dok.app import dok_bp
        app.register_blueprint(dok_bp)
    except:
        pass
    
    # =====================================================================
    # Register G-Forms blueprint (LOUD traceback if fails)
    # Pattern racine package identique a mennem/party/dok/ecole_biblique :
    #   from gforms.app import gforms_bp
    # Le package racine `gforms/` est un adaptateur qui re-expose le
    # blueprint defini dans app.routes.gforms (url_prefix='/forms' est deja
    # porte par le Blueprint lui-meme — ne PAS le repasser ici : double prefixe).
    # Les sources React/Vite du module sont dans le dossier `G-Forms/` a la
    # racine ; si `npm run build` est execute dans G-Forms/, on sert
    # directement G-Forms/dist/index.html, sinon un placeholder est servi.
    # =====================================================================
    try:
        from gforms.app import gforms_bp
        app.register_blueprint(gforms_bp)
        app.logger.info("Registered G-Forms blueprint at /forms (from package gforms/)")
    except Exception as e:
        app.logger.error(f"Failed to register G-Forms blueprint: {type(e).__name__}: {str(e)}")
        import traceback as _tb_gf
        app.logger.error(_tb_gf.format_exc())

    # =====================================================================
    # Register Bank blueprint (LOUD traceback if fails)
    # Pattern racine package identique a mennem/party/dok/ecole_biblique :
    #   from bank.app import bank_bp
    # Le package racine `bank/` est un adaptateur qui re-expose bank_bp
    # defini dans app.routes.bank (url_prefix='/bank' deja dans Blueprint).
    # Le module d'architecture complet (microservices Node) est dans le
    # dossier `glory2yah-bank/` a la racine (specs Glory2Yah_Bank_Blueprint.md).
    # Les templates sont dans templates/ : bank_dashboard / loan_list /
    # loan_apply / investment_products / my_investments / admin_bank.
    # =====================================================================
    try:
        from bank.app import bank_bp
        app.register_blueprint(bank_bp)
        app.logger.info("Registered Bank blueprint at /bank (from package bank/)")
    except Exception as e:
        app.logger.error(f"Failed to register Bank blueprint: {type(e).__name__}: {str(e)}")
        import traceback as _tb_bk
        app.logger.error(_tb_bk.format_exc())


def register_error_handlers(app):
    """Register error handlers — P1 FIX: 500 rolls back session, add security headers on every response"""

    @app.after_request
    def inject_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        if request.is_secure or app.config.get('SESSION_COOKIE_SECURE'):
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        nonce = getattr(request, '_csp_nonce', None)
        if nonce:
            response.headers['Content-Security-Policy'] = (
                "default-src 'self'; "
                f"script-src 'self' 'nonce-{nonce}' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
                "img-src 'self' data: https: blob:; "
                "font-src 'self' https://cdnjs.cloudflare.com data:; "
                "media-src 'self' https: blob:; "
                "connect-src 'self' wss: ws: https:; "
                "frame-src 'self' https:; "
                "object-src 'none'; "
                "base-uri 'self'; "
                "form-action 'self'"
            )
        else:
            response.headers['Content-Security-Policy'] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
                "img-src 'self' data: https: blob:; "
                "font-src 'self' https://cdnjs.cloudflare.com data:; "
                "media-src 'self' https: blob:; "
                "connect-src 'self' wss: ws: https:; "
                "frame-src 'self' https:; "
                "object-src 'none'; "
                "base-uri 'self'; "
                "form-action 'self'"
            )
        return response

    @app.errorhandler(404)
    def not_found(e):
        return render_template('error.html', error=str(getattr(e, 'description', e)), error_code=404), 404

    @app.errorhandler(500)
    def internal_error(e):
        try:
            db.session.rollback()
        except Exception:
            pass
        return render_template('error.html', error=str(getattr(e, 'description', e)), error_code=500), 500

    @app.errorhandler(CSRFError)
    def csrf_error(e):
        """P1 FIX: friendly CSRF error instead of blank white 'Bad Request The CSRF session token is missing.'"""
        from flask import url_for as _uf
        # Session expired / fresh visitor → redirect to where they were (or home) + flash notice.
        # For login/register/posts with CSRF missing → send user back with regeneration (new session + new token).
        msg = (
            "Sesyon ou an ekspire oswa token sekirite pa t la (CSRF token missing). "
            "Tanpri eseye ankò (paj lan te re-chaje avèk nouvo token)."
        )
        try:
            flash(msg, "error")
        except Exception:
            pass
        target = request.referrer or _uf('main.index')
        # Never redirect back to /error page, loop prevention
        if '/error' in target:
            target = _uf('main.index')
        return redirect(target, code=303)


def register_template_filters(app):
    """Register custom Jinja2 filters"""
    import json
    from flask import url_for as flask_url_for
    from app.utils.currency import gkach_to_htg, htg_to_gkach, format_htg
    
    @app.template_filter('gkach_to_htg')
    def gkach_to_htg_filter(value):
        """Convert Gkach to HTG"""
        try:
            return gkach_to_htg(int(value))
        except:
            return 0.0
    
    @app.template_filter('htg_to_gkach')
    def htg_to_gkach_filter(value):
        """Convert HTG to Gkach"""
        try:
            return htg_to_gkach(float(value))
        except:
            return 0
    
    @app.template_filter('format_htg')
    def format_htg_filter(value):
        """Format HTG amount for display"""
        try:
            return format_htg(float(value))
        except:
            return "0.00 HTG"
    
    @app.context_processor
    def inject_currency_functions():
        """Inject currency functions into templates"""
        return dict(
            gkach_to_htg=gkach_to_htg,
            htg_to_gkach=htg_to_gkach,
            format_htg=format_htg,
            GKACH_TO_HTG_RATE=app.config.get('GKACH_TO_HTG_RATE', 1.15)
        )
    
    @app.template_filter('fromjson')
    def fromjson_filter(value):
        if value is None:
            return []
        try:
            return json.loads(value)
        except:
            return []
    
    @app.context_processor
    def override_url_for():
        def url_for_with_fallback(endpoint, **values):
            # Map old endpoints to new blueprint endpoints
            endpoint_map = {
                'index': 'main.index',
                'submit_ad': 'main.submit_ad',
                'reels': 'main.reels',
                'health': 'main.health',
                'login': 'auth.login',
                'register': 'auth.register',
                'logout': 'auth.logout',
                'profile': 'auth.profile',
                'edit_profile': 'auth.edit_profile',
                'my_ads': 'auth.my_ads',
                'edit_ad': 'auth.edit_ad',
                'delete_ad': 'auth.delete_ad',
            }
            
            # Try mapped endpoint first
            if endpoint in endpoint_map:
                try:
                    return flask_url_for(endpoint_map[endpoint], **values)
                except:
                    pass
            
            # Try original endpoint
            try:
                return flask_url_for(endpoint, **values)
            except:
                # Fallback to main.index, then root path
                try:
                    return flask_url_for('main.index', **values)
                except:
                    return '/'
        
        return dict(url_for=url_for_with_fallback)


def setup_logging(app):
    """Setup application logging — persistent on Render, logs land on the persistent
    instance/ disk so they survive deploys. Use app.config['LOG_DIR']."""
    try:
        log_dir = app.config.get('LOG_DIR') or 'logs'
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        log_level = getattr(logging, app.config.get('LOG_LEVEL', 'INFO'))
        file_handler = logging.FileHandler(os.path.join(log_dir, 'glory2yahpub.log'))
        file_handler.setLevel(log_level)
        app.logger.addHandler(file_handler)
        app.logger.setLevel(log_level)
    except Exception as e:
        # If file logging fails, just use stdout
        pass


# Gunicorn entrypoint compatibility:
# Procfile runs `gunicorn app:app ...` which expects an attribute named `app`
# in this module. Provide it using the application factory.
#
# RENDER-SAFE DEFAULT for FLASK_ENV:
#   If RENDER env var / PORT env var (Render convention) is set we default to
#   'production' to avoid accidentally running SQLite on the 'development' SQLite path
#   (which would create an ephemeral SQLite DB wiped on every deploy).
#   Users can still override via FLASK_ENV env var as usual.
from app.config import _on_render as _on_render_guni
_gunicorn_default_env = 'production' if _on_render_guni() else 'development'
app = create_app(os.environ.get('FLASK_ENV', _gunicorn_default_env))
