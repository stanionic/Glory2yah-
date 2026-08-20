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
        # Correct key for flask-limiter >=3.5 (RATELIMIT_STORAGE_URL is legacy/ignored)
        app.config['RATELIMIT_STORAGE_URI'] = 'memory://'
    
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

    @login_manager.unauthorized_handler
    def _unauthorized():
        """Return JSON 401 for AJAX/fetch() calls; redirect browser HTML visits."""
        from flask import jsonify
        wants_json = (
            request.is_json
            or (request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html)
            or request.headers.get('X-Requested-With', '').lower() == 'xmlhttprequest'
        )
        if wants_json:
            login_url = url_for(login_manager.login_view, next=request.path or '/')
            resp = jsonify({
                'success': False,
                'error': login_manager.login_message or 'Unauthorized',
                'login_redirect': login_url,
            })
            resp.status_code = 401
            return resp
        return redirect(url_for(login_manager.login_view, next=request.path or request.args.get('next') or '/'))

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
        candidates = []
        cfg_up = _cup.config.get('UPLOAD_FOLDER')
        if cfg_up:
            candidates.append(_os_up.path.abspath(cfg_up))
        static_root = app.static_folder or _os_up.path.join(app.root_path, '..', 'static')
        candidates.append(_os_up.path.join(static_root, 'uploads'))
        try:
            candidates.append(_os_up.path.join(app.instance_path, 'uploads'))
        except Exception:
            pass
        try:
            candidates.append(_os_up.path.abspath(_os_up.join(app.root_path, '..', 'instance', 'uploads')))
        except Exception:
            pass
        seen = set()
        for cand_dir in candidates:
            if not cand_dir or cand_dir in seen:
                continue
            seen.add(cand_dir)
            target = _os_up.path.join(cand_dir, safe_fn)
            if _os_up.path.isfile(target):
                return send_from_directory(cand_dir, safe_fn)
        _abort_up(404)

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
        # Multi-fallback candidates (same 4 as /uploads/<filename> route):
        #   1) app.config UPLOAD_FOLDER  (canonical Render persistent disk path)
        #   2) static/uploads legacy     (already checked above, skip)
        #   3) app.instance_path/uploads (flask canonical instance folder)
        #   4) <root>/../instance/uploads (Render relative path from container)
        candidates = []
        cfg_dir = app.config.get('UPLOAD_FOLDER')
        if cfg_dir:
            candidates.append(_os_sb.path.abspath(cfg_dir))
        try:
            candidates.append(_os_sb.path.join(app.instance_path, 'uploads'))
        except Exception:
            pass
        try:
            candidates.append(_os_sb.path.abspath(_os_sb.join(app.root_path, '..', 'instance', 'uploads')))
        except Exception:
            pass
        seen = set()
        for cand_dir in candidates:
            if not cand_dir or cand_dir in seen:
                continue
            seen.add(cand_dir)
            cand_target = _os_sb.path.join(cand_dir, safe_match)
            if _os_sb.path.isfile(cand_target):
                return _sfd(cand_dir, safe_match)
        _abt(404)

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
        """
        Global template data — cart_count / gkach_balance / is_logged_in.

        DEFENSIVE GUARD (fixes "connected users can't load ADS"):
          This context processor runs ON EVERY template render. It is the ONLY
          code path in the entire request that differs between anonymous and
          logged-in users for the main ADS-loading routes (/, /mache).

          A single uncaught exception in ANY of the service calls below would
          bubble up through flask's render_template → be caught by the route's
          blanket "except Exception" → which returns products=[], giving the
          exact symptom logged-in users reported: "ADS don't load".

          STRATEGY:
            * OUTERMOST try/except that ALWAYS returns a valid `data` dict,
              never propagates.
            * Each service call is wrapped INDIVIDUALLY so one bad call doesn't
              skip the others.
            * `current_user` is a lazy Flask-Login LocalProxy — even accessing
              `.is_authenticated` can trigger the user loader and raise. We
              guard EVERY attribute access.
        """
        # Sensible defaults — returned immediately on any catastrophic failure
        _defaults = {
            'is_logged_in': False,
            'cart_count': 0,
            'gkach_balance': 0,
        }
        try:
            from flask_login import current_user
        except Exception:
            return dict(_defaults)

        data = dict(_defaults)

        try:
            # Lazy-proxy guard: use getattr for every attribute access
            _auth = False
            try:
                _auth = bool(current_user and getattr(current_user, 'is_authenticated', False))
            except Exception:
                _auth = False
            data['is_logged_in'] = _auth

            if _auth:
                # ---- CartService: independent try ------------------------------------
                try:
                    from app.services.cart_service import CartService
                    _uid = getattr(current_user, 'id', None)
                    if _uid is not None:
                        totals = CartService.calculate_totals(_uid)
                        if isinstance(totals, dict):
                            data['cart_count'] = int(totals.get('count') or 0)
                except Exception as _ce:
                    try:
                        app.logger.error(f"inject_global_data CartService: {_ce}")
                    except Exception:
                        pass

                # ---- GkachService: independent try ------------------------------------
                try:
                    from app.services.gkach_service import GkachService
                    _wa = getattr(current_user, 'whatsapp', None)
                    if _wa:
                        data['gkach_balance'] = int(GkachService.get_balance(_wa) or 0)
                except Exception as _ge:
                    try:
                        app.logger.error(f"inject_global_data GkachService: {_ge}")
                    except Exception:
                        pass
        except Exception as _outer:
            # LAST LINE OF DEFENSE — never leak an exception to flask/jinja
            try:
                app.logger.error(f"inject_global_data OUTER failure (fallback to defaults): {_outer}")
            except Exception:
                pass
            return dict(_defaults)

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
        # Import events models (EVENTS / SOS ALO LEGLIZ module) so their tables
        # are created by db.create_all() and relationships resolve.
        from app.models.events import (
            Event, EventLeader, EventProgramItem, EventFaq, EventNews,
            EventMedia, EventRegion, EventCoordinator, EventParticipant,
            EventOrganization, seed_events,
        )
        db.create_all()

        # Seed the SOS ALO LEGLIZ event (idempotent, safe to re-run)
        try:
            seed_events()
        except Exception as _ev_seed_e:
            db.session.rollback()
            app.logger.warning(
                f'EVENTS seed skipped ({type(_ev_seed_e).__name__}): {_ev_seed_e}')

        # =====================================================================
        # ADS PERSISTENCE GUARD (Summary §6 + user explicit request 2026-08-10)
        #   Goal: 100% prove at BOOTSTRAP time that approved ads / user ads were
        #   NOT erased between commits / deploys.
        #
        #   Steps:
        #   (A) Log BEFORE + AFTER row counts: ads rows / approved / pending /
        #       images-only / paid — so diffing two consecutive app-start logs
        #       instantly tells you if rows vanished (vs filter bugs hiding them).
        #   (B) If running on Render (RENDER env var present) AND the resolved
        #       DSN is SQLite: CRITICAL WARNING unless the sqlite file path lives
        #       UNDER the persistent disk mount (/opt/render/project/src/instance).
        #   (C) Same sanity check for upload folder (ads images): must be on the
        #       persistent disk on Render, else images uploaded get wiped on every
        #       commit / rebuild → looks like ads disappeared.
        #
        #   Zero writes / no mutations — pure read-only diagnostic + warning log.
        # =====================================================================
        def _ads_persistence_snapshot(stage_label: str):
            """Count ads rows (various statuses) and return short dict.
            Swallow all errors — persistence guard must never crash app startup."""
            try:
                from app.models.ad import Ad as _Ad
                q = _Ad.query
                total = q.count()
                approved = q.filter_by(admin_status='approved').count()
                pending = q.filter_by(admin_status='pending').count()
                rejected = q.filter_by(admin_status='rejected').count()
                paid = q.filter_by(payment_status='paid').count()
                sell_type = q.filter_by(ad_type='sell').count()
                publish_type = q.filter_by(ad_type='publish').count()
                app.logger.info(
                    f"ADS PERSISTENCE [{stage_label}] TOTAL={total} | APPROVED={approved} | "
                    f"PENDING={pending} | REJECTED={rejected} | PAID={paid} | "
                    f"SELL={sell_type} | PUBLISH={publish_type}"
                )
                return dict(total=total, approved=approved, pending=pending, rejected=rejected,
                            paid=paid, sell=sell_type, publish=publish_type)
            except Exception as _pg_e:
                app.logger.warning(
                    f"ADS PERSISTENCE [{stage_label}] count skipped (probably tables not yet "
                    f"created on first run): {type(_pg_e).__name__}: {_pg_e}"
                )
                return None
        _snap_before = _ads_persistence_snapshot("BEFORE-migrations")

        # --- Render-specific guard: SQLite file MUST be on persistent disk -----
        try:
            _on_render_env = bool(_os.environ.get('RENDER') or _os.environ.get('RENDER_SERVICE_ID') or
                                  'onrender.com' in (_os.environ.get('RENDER_EXTERNAL_HOSTNAME') or '').lower())
            if _on_render_env:
                import re as _re_pg
                dsn = str(app.config.get('SQLALCHEMY_DATABASE_URI') or '')
                # 1) DSN safety
                if dsn.lower().startswith('sqlite:///'):
                    # sqlite:///path/to.db OR sqlite:// (memory)
                    if dsn == 'sqlite://' or dsn.startswith('sqlite:///:'):
                        app.logger.critical(
                            "ADS PERSISTENCE CRITICAL: on Render but SQLite URL is IN-MEMORY "
                            "(empty/sqlite:///) — ALL ADS + users WILL BE WIPED on every "
                            "commit / deploy / restart. Set DATABASE_URL to PostgreSQL managed "
                            "database on Render or set SQLALCHEMY_DATABASE_URI to a file under "
                            "/opt/render/project/src/instance/.")
                    else:
                        path_part = dsn[len('sqlite:///'):]
                        norm = path_part.replace('\\', '/')
                        if not norm.startswith('/opt/render/project/src/instance/') and \
                           '/instance/' not in norm:
                            app.logger.critical(
                                f"ADS PERSISTENCE CRITICAL: on Render SQLite file NOT on "
                                f"persistent disk. DSN file path={path_part!r}. Must be under "
                                f"/opt/render/project/src/instance/ to survive commit/rebuild. "
                                f"Verify DATABASE_URL env / ProductionConfig fallback.")
                        else:
                            app.logger.info(
                                f"ADS PERSISTENCE: SQLite file ON persistent Render disk: {path_part}")
                elif dsn.lower().startswith('postgresql'):
                    app.logger.info(
                        "ADS PERSISTENCE: using managed PostgreSQL (DSN postgresql://…[redacted 5 chars]…). "
                        "ADS rows will SURVIVE every commit / deploy / rebuild.")
                else:
                    app.logger.warning(f"ADS PERSISTENCE: unknown DSN scheme: {dsn[:20]}… (no check)")

                if _os.environ.get('G2Y_PG_FALLBACK_ACTIVE') == '1':
                    app.logger.critical(
                        "PRODUCTION DB FALLBACK ACTIVE: DATABASE_URL was empty at boot (Render "
                        "PostgreSQL managed env not yet injected / first-deploy race condition). "
                        "App is running with a TEMPORARY PERSISTENT SQLite under /instance/. "
                        "ACTION: 1) Check Render Dashboard → glory2yahpub → Environment → "
                        "DATABASE_URL (fromDatabase glory2yahpub-db connectionString must be "
                        "green). 2) Trigger a manual deploy so the container restarts WITH the "
                        "proper PostgreSQL DSN. 3) Optional: set env DB_ENFORCE_POSTGRES_PRODUCTION=1 "
                        "to NEVER use fallback (strict pipelines). NOTE: ads created while "
                        "fallback is active stay in the local SQLite file and will NOT migrate "
                        "to PostgreSQL automatically — switch to PG soon."
                    )
                    # Detect the exact "NO ADS AT ALL" incident: the fallback file is a fresh
                    # db.create_all() (empty ads table) while the real ads live in the
                    # persistent-disk SQLite (instance/glory2yahpub_dev.db) — i.e. production
                    # served 0 ads ("connected users can't load ADS"). Make it visible in logs.
                    try:
                        from app.models.ad import Ad as _AdFb
                        _fb_tot = _AdFb.query.count()
                        _fb_appr = _AdFb.query.filter_by(admin_status='approved').count()
                        if _fb_appr == 0:
                            app.logger.critical(
                                f"PRODUCTION DB FALLBACK ACTIVE: fallback SQLite has {_fb_tot} ads "
                                f"({_fb_appr} approved) — production serves NO ADS. Restore data: "
                                f"in Render Shell run  python backup_db.py  then  "
                                f"python migrate_sqlite_to_postgres.py --target \"$DATABASE_URL\"  "
                                f"(source = instance/glory2yahpub_dev.db on the persistent disk; "
                                f"see MIGRATION_RENDER.md)."
                            )
                    except Exception as _efb:
                        app.logger.warning(
                            f"PRODUCTION DB FALLBACK ACTIVE: ads-count probe skipped: {_efb}"
                        )

                # 2) UPLOAD_FOLDER safety (ads images)
                _up = str(app.config.get('UPLOAD_FOLDER') or '').replace('\\', '/').rstrip('/')
                if _on_render_env and _up:
                    if not _up.startswith('/opt/render/project/src/instance/'):
                        app.logger.critical(
                            f"ADS PERSISTENCE CRITICAL: UPLOAD_FOLDER={_up!r} is NOT on "
                            f"persistent Render disk. Every uploaded ad IMAGE will be WIPED on "
                            f"commit/rebuild. Fix: set env UPLOAD_FOLDER to "
                            f"/opt/render/project/src/instance/uploads as in render.yaml.")
                    else:
                        app.logger.info(f"ADS PERSISTENCE: UPLOAD_FOLDER OK on Render disk: {_up}")
        except Exception as _e_pg2:
            app.logger.warning(f"ADS PERSISTENCE (Render guard skipped): {type(_e_pg2).__name__}: {_e_pg2}")

        # =====================================================================
        # EVENTS MIGRATION: add the organization address field to existing
        # databases. db.create_all() does not alter existing tables.
        # =====================================================================
        try:
            from sqlalchemy import inspect as _event_inspect
            from sqlalchemy import text as _event_text
            _event_insp = _event_inspect(db.engine)
            if _event_insp.has_table('event_organizations'):
                _event_org_cols = {c['name'] for c in _event_insp.get_columns('event_organizations')}
                if 'address' not in _event_org_cols:
                    db.session.execute(_event_text(
                        'ALTER TABLE event_organizations ADD COLUMN address VARCHAR(255)'))
                    db.session.commit()
                    app.logger.info('EVENTS MIGRATION: added event_organizations.address column')
            if _event_insp.has_table('event_coordinators'):
                _event_coord_cols = {c['name'] for c in _event_insp.get_columns('event_coordinators')}
                _event_coord_additions = {
                    'org_name': 'VARCHAR(255)',
                    'org_type': 'VARCHAR(30)',
                    'city': 'VARCHAR(120)',
                    'address': 'VARCHAR(255)',
                    'approx_participants': 'INTEGER',
                }
                for _event_coord_col, _event_coord_type in _event_coord_additions.items():
                    if _event_coord_col not in _event_coord_cols:
                        db.session.execute(_event_text(
                            f'ALTER TABLE event_coordinators ADD COLUMN {_event_coord_col} {_event_coord_type}'))
                db.session.commit()
        except Exception as _event_migration_error:
            db.session.rollback()
            app.logger.warning(
                f'EVENTS MIGRATION: could not add organization address column: {_event_migration_error}')

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

        # =====================================================================
        # KONFERANS → E-LEARNING MIGRATION (idempotent): extend konferans_rooms
        # table with new columns introduced by PHASE 2.
        # Existing classic rooms keep room_type='classic' (NULL = classic as well
        # for backwards compat). All fields are NULLABLE so old rows remain fully
        # readable by existing code paths. Zero breaking changes.
        # =====================================================================
        try:
            from sqlalchemy import inspect as _sa_inspect_elkr
            from sqlalchemy import text as _sa_text_elkr
            _insp_elkr = _sa_inspect_elkr(db.engine)
            if _insp_elkr.has_table('konferans_rooms'):
                _kr_cols = {c['name'] for c in _insp_elkr.get_columns('konferans_rooms')}
                _kr_adds: list[tuple[str, str]] = [
                    ('room_type',      "VARCHAR(16) DEFAULT 'classic'"),
                    ('class_id',       "INTEGER DEFAULT NULL"),
                    ('lesson_id',      "INTEGER DEFAULT NULL"),
                    ('scheduled_at',   "DATETIME DEFAULT NULL"),
                    ('started_at',     "DATETIME DEFAULT NULL"),
                    ('ended_at',       "DATETIME DEFAULT NULL"),
                    ('max_participants', "INTEGER DEFAULT 50"),
                    ('mic_locked',     "BOOLEAN DEFAULT FALSE"),
                    ('cam_locked',     "BOOLEAN DEFAULT FALSE"),
                    ('chat_locked',    "BOOLEAN DEFAULT FALSE"),
                    ('class_locked',   "BOOLEAN DEFAULT FALSE"),
                    ('whiteboard_id',  "INTEGER DEFAULT NULL"),
                ]
                _kr_altered = 0
                for _col, _dcl in _kr_adds:
                    if _col not in _kr_cols:
                        try:
                            db.session.execute(
                                _sa_text_elkr(f'ALTER TABLE konferans_rooms ADD COLUMN {_col} {_dcl}')
                            )
                            db.session.commit()
                            _kr_altered += 1
                        except Exception:
                            db.session.rollback()
                if _kr_altered:
                    app.logger.info(
                        f'KONFERANS E-LEARNING MIGRATION: added {_kr_altered} '
                        f'columns to konferans_rooms ({", ".join(c for c,_ in _kr_adds if c not in _kr_cols)})'
                    )
                _elkr_idx_name = 'ix_konferans_rooms_lesson_class'
                try:
                    _kr_indexes = {
                        ix['name'] for ix in _insp_elkr.get_indexes('konferans_rooms')
                    }
                except Exception:
                    _kr_indexes = set()
                if _elkr_idx_name not in _kr_indexes:
                    try:
                        db.session.execute(_sa_text_elkr(
                            'CREATE INDEX IF NOT EXISTS ix_konferans_rooms_lesson_class '
                            'ON konferans_rooms (class_id, lesson_id, scheduled_at)'
                        ))
                        db.session.commit()
                    except Exception:
                        db.session.rollback()
        except Exception as _elkr_e:
            db.session.rollback()
            app.logger.warning(f'KONFERANS E-LEARNING MIGRATION: skipped: {_elkr_e}')
        
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

        # =====================================================================
        # PERSISTENCE DISK GUARD + STAGING CLEANUP (BOOT TIME)
        #   - Creates the .uploads_persistent_marker.txt marker file on the
        #     Render persistent disk. If file cannot be written AND we're on
        #     Render → disk mount is MISSING → images would be erased by the
        #     next deploy → emit CRITICAL WARNING.
        #   - Deletes staging files older than STAGING_TTL_DAYS (default 30d).
        #   - Confirms staging/backup folders exist and are writable.
        # =====================================================================
        _disk_guard_ok = True
        _disk_guard_note = '✅ Marker guard OK — persistent disk is mounted'
        try:
            import os as _os_g
            import time as _time_g
            marker_file = app.config.get('PERSISTENCE_MARKER_FILE')
            stage_dir = app.config.get('STAGING_UPLOAD_FOLDER')
            backup_dir = app.config.get('BACKUP_UPLOAD_FOLDER')
            ttl_days = int(app.config.get('STAGING_TTL_DAYS', 30) or 30)
            if marker_file:
                try:
                    with open(marker_file, 'a', encoding='utf-8') as _mf:
                        _mf.write(
                            f'[boot {_time_g.strftime("%Y-%m-%d %H:%M:%S UTC", _time_g.gmtime())}] '
                            f'pid={_os_g.getpid()} persistent=1\n'
                        )
                    # Read back to confirm actual persistence (test previous writes survived)
                    if _os_g.path.exists(marker_file) and _os_g.path.getsize(marker_file) > 10:
                        _disk_guard_ok = True
                    else:
                        _disk_guard_ok = False
                        _disk_guard_note = '❌ Marker guard FAIL — fichier marker introuvable/trop court'
                except Exception as _e_mk:
                    _disk_guard_ok = False
                    _disk_guard_note = f'⚠️ Marker guard FAIL — impossible écrire marker: {_e_mk!r}'
            # Enforce Render presence check for loud warnings
            on_render_heur = bool(
                _os_g.environ.get('RENDER') or _os_g.environ.get('RENDER_SERVICE_ID')
                or (_os_g.environ.get('PORT') and _os_g.environ.get('PORT') not in ('5000','','None'))
            )
            if on_render_heur and not _disk_guard_ok:
                app.logger.critical(
                    'DISK GUARD CRITICAL RENDER: Persistent disk is NOT properly mounted! '
                    'Uploads/backups/staging will be ERASED on next deploy. '
                    'Fix: Render → Dashboard → Disks → Mount Path MUST be /opt/render/project/src/instance. '
                    f'Note: {_disk_guard_note}'
                )
            # ---- Staging TTL cleanup: remove staging files older than ttl_days ----
            removed_count = 0
            removed_bytes = 0
            if stage_dir and _os_g.path.isdir(stage_dir):
                now_ts = _time_g.time()
                cutoff = now_ts - (ttl_days * 86400)
                for _entry in _os_g.scandir(stage_dir):
                    try:
                        if not _entry.is_file(follow_symlinks=False):
                            continue
                        st = _entry.stat(follow_symlinks=False)
                        if st.st_mtime < cutoff:
                            _os_g.unlink(_entry.path)
                            removed_count += 1
                            removed_bytes += int(getattr(st, 'st_size', 0) or 0)
                    except Exception:
                        pass
                if removed_count:
                    app.logger.info(
                        f'STAGING TTL: removed {removed_count} stale staging files '
                        f'(≈{round(removed_bytes/1024/1024,1)} MB, TTL={ttl_days}d)'
                    )
        except Exception as _e_guard:
            _disk_guard_ok = False
            try:
                app.logger.warning(f'PERSISTENCE GUARD: boot hook failed (non-fatal): {_e_guard!r}')
            except Exception:
                pass

        # =====================================================================
        # STARTUP PERSISTENCE BANNER — RASSURER L'UTILISATEUR
        # (L'utilisateur a peur que les données soient effacées à chaque commit
        # GitHub. On affiche EXPLICITEMENT en console l'état de la persistance.)
        # =====================================================================
        try:
            import os as _os_pb
            db_uri = app.config.get('SQLALCHEMY_DATABASE_URI') or ''
            if db_uri.startswith('postgresql'):
                db_scheme = 'PostgreSQL (Render Managed)'
                db_note = 'Hébergé par Render — SURVIT À TOUS LES COMMITS / DEPLOYS'
            elif db_uri.startswith('sqlite'):
                db_scheme = 'SQLite Persistant'
                db_note = 'Fichier dans instance/ — SURVIT À TOUS LES COMMITS / DEPLOYS'
            else:
                db_scheme = db_uri.split('://')[0] if '://' in db_uri else 'Inconnu'
                db_note = 'Vérifier configuration'
            upload_folder = app.config.get('UPLOAD_FOLDER') or '(non défini)'
            stage_folder_b = app.config.get('STAGING_UPLOAD_FOLDER') or '-'
            backup_folder_b = app.config.get('BACKUP_UPLOAD_FOLDER') or '-'
            render_disk_path = '/opt/render/project/src/instance'
            on_render_disk = render_disk_path in _os_pb.path.abspath(upload_folder) if upload_folder != '(non défini)' else False
            disk_note = '✅ Sur Render Persistent Disk 1GB — JAMAIS effacé par git push' if on_render_disk else ('⚠️ Local dev — vérifier .gitignore exclut ce dossier')
            guard_note = _disk_guard_note if '_disk_guard_note' in dir() else '⚠️ Guard non vérifié'
            banner_lines = [
                '',
                '╔══════════════════════════════════════════════════════════════════════════════╗',
                '║  CONFORT UTILISATEUR — PERSISTANCE DES DONNÉES                               ║',
                '╠══════════════════════════════════════════════════════════════════════════════╣',
                f'║  BASE DE DONNÉES : {db_scheme:<62}║',
                f'║  Statut BD       : {db_note:<62}║',
                f'║  Chemin UPLOAD   : {upload_folder[:62]:<62}║',
                f'║  Statut Images   : {disk_note[:62]:<62}║',
                f'║  Staging PRE-PG  : {stage_folder_b[:62]:<62}║',
                f'║  Backup mirror   : {backup_folder_b[:62]:<62}║',
                f'║  Guard disk      : {guard_note[:62]:<62}║',
                '║                                                                              ║',
                '║  Protection GIT (fichier .gitignore) :                                       ║',
                '║    • *.db              → EXCLU de git (jamais commités)                      ║',
                '║    • instance/         → EXCLU de git (disque persistent Render)             ║',
                '║    • static/uploads/   → EXCLU de git (dossier uploads legacy)               ║',
                '║    • uploads_staging/  → EXCLU (zone pre-POSTGRES anti-effacement)           ║',
                '║    • uploads_backup/   → EXCLU (snapshot miroir sur disque persistant)       ║',
                '║                                                                              ║',
                '║  ⚠️ RAPPEL IMPORTANT : Vos images et BD NE SERONT JAMAIS EFFACÉES             ║',
                '║  par un git commit / git push. Les données vivent SUR LE DISQUE PERSISTENT   ║',
                '║  1GB de Render (mountPath: /opt/render/project/src/instance), PAS dans       ║',
                '║  le conteneur de build éphémère. Chaque deploy RECRÉE le symlink :           ║',
                '║    static/uploads  →  instance/uploads (disque persistent)                   ║',
                '╚══════════════════════════════════════════════════════════════════════════════╝',
                '',
            ]
            for bl in banner_lines:
                try:
                    app.logger.info(bl)
                except Exception:
                    try:
                        print(bl)
                    except Exception:
                        pass
        except Exception as _e_pb_banner:
            try:
                app.logger.warning(f'PERSISTENCE BANNER: échec affichage: {_e_pb_banner}')
            except Exception:
                pass

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
        # Admin user bootstrap — SECURE & IDEMPOTENT:
        #   SECURITY FIX v2.0:
        #   - Password is ONLY set on initial creation, NOT on every boot
        #   - Password defaults to 'StanGlory2YahPub1986' ONLY in development
        #   - In production: ADMIN_PASSWORD environment variable is REQUIRED
        #   - Existing admin passwords are NEVER overwritten
        #   - Pseudo/WhatsApp fields MAY be synchronized (non-critical)
        # =====================================================================
        try:
            admin_phone    = _os.environ.get('ADMIN_WHATSAPP', '+50942882076')
            admin_password = _os.environ.get('ADMIN_PASSWORD', None)  # Changed: None instead of default
            admin_pseudo   = _os.environ.get('ADMIN_PSEUDO',   'Admin509')
            admin_name     = _os.environ.get('ADMIN_NAME',     'Glory2YahPub')
            admin_user = None
            
            # Search for existing admin: first by pseudo, then by phone, then any admin
            if admin_pseudo:
                admin_user = User.query.filter(User.pseudo.ilike(admin_pseudo)).first()
            if (not admin_user) and admin_phone:
                admin_user = User.query.filter_by(whatsapp=admin_phone).first()
            if not admin_user:
                any_admin = User.query.filter_by(is_admin=True).first()
                if any_admin:
                    admin_user = any_admin
            
            if not admin_user:
                # No admin exists → CREATE (password is REQUIRED)
                if not admin_password:
                    # In development: use default; in production: REQUIRE env var
                    if config_name == 'production':
                        app.logger.error(
                            "SECURITY: No admin exists and ADMIN_PASSWORD not set. "
                            "In production, ADMIN_PASSWORD environment variable is REQUIRED."
                        )
                    else:
                        # Development only: use default
                        admin_password = 'StanGlory2YahPub1986'
                        app.logger.warning(
                            "Development mode: using default admin password. "
                            "Set ADMIN_PASSWORD environment variable to override."
                        )
                
                if admin_password:
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
                        f"(password set from {'ADMIN_PASSWORD env var' if _os.environ.get('ADMIN_PASSWORD') else 'development default'})"
                    )
            else:
                # Admin exists → SYNCHRONIZE non-critical fields only (NO password reset)
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
                # SECURITY FIX: Do NOT reset password on every boot
                # Password is only set during account creation, not synchronized on boot
                if admin_user.auth_provider != 'whatsapp':
                    admin_user.auth_provider = 'whatsapp'
                    changed = True
                if changed:
                    # Ensure UserGkach row exists (for old migrations)
                    g = UserGkach.query.filter(
                        (UserGkach.user_id == admin_user.id) |
                        (UserGkach.user_whatsapp == admin_user.whatsapp)
                    ).first()
                    if not g:
                        db.session.add(UserGkach(user_id=admin_user.id, user_whatsapp=admin_user.whatsapp, gkach_balance=0))
                    db.session.commit()
                    app.logger.info(
                        f"Admin user SYNCHRONIZED: pseudo={admin_user.pseudo!r} "
                        f"whatsapp={admin_user.whatsapp!r} is_admin={admin_user.is_admin} "
                        f"(password NOT reset - preserved from previous boot)"
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

        # =====================================================================
        # ADS PERSISTENCE GUARD — 2nd snapshot AFTER migrations + seeds.
        #   If AFTER < BEFORE for APPROVED → something just ERASED approved
        #   ads during this bootstrap (should NEVER happen). Log CRITICAL so
        #   admins see it immediately.
        # =====================================================================
        try:
            from app.models.ad import Ad as _AdPost
            _snap_after = {
                'total': _AdPost.query.count(),
                'approved': _AdPost.query.filter_by(admin_status='approved').count(),
                'pending': _AdPost.query.filter_by(admin_status='pending').count(),
                'rejected': _AdPost.query.filter_by(admin_status='rejected').count(),
                'paid': _AdPost.query.filter_by(payment_status='paid').count(),
                'sell': _AdPost.query.filter_by(ad_type='sell').count(),
                'publish': _AdPost.query.filter_by(ad_type='publish').count(),
            }
            app.logger.info(
                f"ADS PERSISTENCE [AFTER-migrations+seeds] "
                f"TOTAL={_snap_after['total']} | APPROVED={_snap_after['approved']} | "
                f"PENDING={_snap_after['pending']} | REJECTED={_snap_after['rejected']} | "
                f"PAID={_snap_after['paid']} | SELL={_snap_after['sell']} | "
                f"PUBLISH={_snap_after['publish']}"
            )
            # Diff check vs BEFORE snapshot
            if _snap_before:
                diff = {k: _snap_after[k] - _snap_before.get(k, 0) for k in _snap_after}
                if diff['approved'] < 0 or diff['total'] < 0:
                    app.logger.critical(
                        f"ADS PERSISTENCE CRITICAL: approved ads DECREASED during bootstrap! "
                        f"BEFORE={_snap_before.get('approved')} → AFTER={_snap_after['approved']} "
                        f"(Δ approved={diff['approved']}, Δ total={diff['total']}). "
                        f"Diff full: {diff}"
                    )
                else:
                    app.logger.info(
                        f"ADS PERSISTENCE [DIFF BEFORE→AFTER] Δ total={diff['total']:+d}, "
                        f"Δ approved={diff['approved']:+d}, Δ pending={diff['pending']:+d} — "
                        f"{'(no ads lost)' if diff['approved'] >= 0 and diff['total'] >= 0 else '(WARN)'}"
                    )
        except Exception as _e_pg3:
            app.logger.warning(
                f"ADS PERSISTENCE (AFTER snapshot skipped): {type(_e_pg3).__name__}: {_e_pg3}"
            )

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
    
    # Register EVENTS blueprint (public) + admin events blueprint
    try:
        from app.routes.events import events_bp, admin_events_bp
        app.register_blueprint(events_bp)
        app.register_blueprint(admin_events_bp)
        app.logger.info('Registered EVENTS blueprint at /events (+ /admin/events)')
    except Exception as e:
        app.logger.warning(f"Could not register EVENTS blueprint: {e}")
    
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

    # =====================================================================
    # Register E-LEARNING blueprint — Phase 2 architecture skeleton.
    #   Module lives under app/routes/elearning/ (package).
    #   url_prefix='/e-learning' is already set on the Blueprint constructor
    #   (don't re-pass it here to avoid double prefixing).
    #   All tables are el_* prefixed; all templates live in templates/elearning/
    #   so the existing Konferans routes and views remain fully untouched
    #   (non-breaking extension — see plan PHASE 2 §21 rule).
    # =====================================================================
    try:
        from app.routes.elearning import elearning_bp
        app.register_blueprint(elearning_bp)
        app.logger.info("Registered E-LEARNING blueprint at /e-learning (from package app/routes/elearning/)")
    except Exception as e:
        app.logger.error(f"Failed to register E-LEARNING blueprint: {type(e).__name__}: {str(e)}")
        import traceback as _tb_el
        app.logger.error(_tb_el.format_exc())



def register_error_handlers(app):
    """Register error handlers — P1 FIX: 500 rolls back session, add security headers on every response"""

    @app.after_request
    def inject_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        # Permissions-Policy: restrict access to powerful APIs
        response.headers['Permissions-Policy'] = (
            'geolocation=(), '
            'microphone=(), '
            'camera=(), '
            'payment=(), '
            'usb=(), '
            'magnetometer=(), '
            'gyroscope=(), '
            'accelerometer=()'
        )
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
    from flask import url_for as flask_url_for, request as flask_request
    from app.utils.currency import gkach_to_htg, htg_to_gkach, format_htg

    def _resolve_base_url():
        """Return a canonical base URL (scheme + host + port) for absolute external URLs
        required by og:image / og:url tags. Always ends without trailing slash.

        Resolution order (most reliable first):
        1. Explicit SITE_URL env var (recommended for production Render)
        2. Within a request context: use request.url_root, honor X-Forwarded-Proto/Host
        3. SERVER_NAME + PREFERRED_URL_SCHEME Flask config if set
        4. Fallback to http://localhost for dev/tests (not used by crawlers).
        """
        import os as _os
        env_url = (_os.environ.get('SITE_URL') or '').strip().rstrip('/')
        if env_url:
            return env_url
        # Within request: honor X-Forwarded headers (Render/Heroku proxy behavior)
        try:
            if flask_request and flask_request.environ:
                scheme = (flask_request.headers.get('X-Forwarded-Proto') or
                          flask_request.environ.get('wsgi.url_scheme') or 'http').split(',')[0].strip()
                host = (flask_request.headers.get('X-Forwarded-Host') or
                        flask_request.host or flask_request.environ.get('HTTP_HOST') or
                        'localhost')
                host = host.split(',')[0].strip()
                return f"{scheme}://{host}".rstrip('/')
        except Exception:
            pass
        server_name = app.config.get('SERVER_NAME')
        if server_name:
            scheme = app.config.get('PREFERRED_URL_SCHEME') or 'https'
            return f"{scheme}://{server_name}".rstrip('/')
        return 'http://localhost'

    def _absolute_static_upload_url(filename):
        """Build the full absolute URL for a file stored under UPLOAD_FOLDER.

        Path rules on this project (see app/__init__.py uploads middleware PHASE1 fix):
          * Files physically live at config UPLOAD_FOLDER (instance/uploads/ on Render).
          * They are publicly served from both:
              - /static/uploads/<filename>  (middleware redirect + symlink compat)
              - /uploads/<filename>         (explicit route in before_request)
        For OG crawlers we emit the canonical /uploads/<abs filename> path under the
        resolved base URL.
        """
        if not filename:
            return ''
        base = _resolve_base_url()
        fname = str(filename).strip().lstrip('/\\').replace('\\', '/')
        # Already absolute URL (http/https) — return as-is
        if fname.lower().startswith('http://') or fname.lower().startswith('https://'):
            return fname
        # Strip any "/static/uploads/" or "uploads/" prefix so we normalize to "/uploads/<name>"
        for prefix in ('static/uploads/', 'uploads/'):
            if fname.startswith(prefix):
                fname = fname[len(prefix):]
        return f"{base}/uploads/{fname}"


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
    
    @app.context_processor
    def inject_og_helpers():
        """Inject absolute URL helpers so templates can emit crawler-friendly OG tags.

        Exposed names (all templates):
          * absolute_base_url() -> str "https://glory2yah.onrender.com"
          * absolute_upload_url('image.png') -> full URL for /uploads/image.png
          * absolute_ad_url(ad_id)       -> full canonical URL to /ad/<ad_id>
          * absolute_share_url(ad_id)    -> full short share URL /s/<ad_id>
        """
        from flask import url_for as _u
        def _base():
            return _resolve_base_url()
        def _abs_upload(filename):
            return _absolute_static_upload_url(filename)
        def _abs_ad(ad_id):
            try:
                path = flask_url_for('main.view_ad', ad_id=ad_id)
            except Exception:
                path = f'/ad/{ad_id}'
            return _base() + path
        def _abs_share(ad_id):
            try:
                path = flask_url_for('share.single_ad', short_id=ad_id)
            except Exception:
                path = f'/s/{ad_id}'
            return _base() + path
        return dict(
            absolute_base_url=_base,
            absolute_upload_url=_abs_upload,
            absolute_ad_url=_abs_ad,
            absolute_share_url=_abs_share,
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
