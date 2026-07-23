"""
Glory2YahPub Application Factory
Modern Flask application with Redis caching and modular architecture
"""
import os
import logging
from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
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
    
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    cache.init_app(app)
    # Initialize SocketIO with Redis if available
    if redis_client:
        socketio.init_app(app, cors_allowed_origins="*", message_queue=app.config['REDIS_URL'])
    else:
        socketio.init_app(app, cors_allowed_origins="*")
        app.logger.warning('SocketIO running without Redis message queue')
    
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Ou dwe konekte pou aksede paj sa a.'
    
    # Custom template filter to get video embed URL
    @app.template_filter('get_embed_url')
    def get_embed_url(url):
        import re
        if not url:
            return None
        url = url.strip()
        youtube_regex = r'(?:youtube\.com\/(?:watch\?v=|shorts\/|embed\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})'
        youtube_match = re.search(youtube_regex, url)
        if youtube_match:
            video_id = youtube_match.group(1)
            return f'https://www.youtube.com/embed/{video_id}?autoplay=1&mute=1'
        vimeo_regex = r'(?:vimeo\.com\/)([0-9]+)'
        vimeo_match = re.search(vimeo_regex, url)
        if vimeo_match:
            video_id = vimeo_match.group(1)
            return f'https://player.vimeo.com/video/{video_id}?autoplay=1&muted=1'
        return None
    
    @login_manager.user_loader
    def load_user(user_id):
        from app.models.user import User
        return User.query.get(int(user_id))
    
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
        from app.models.batch import Batch
        from app.models.batch_ad import BatchAd
        from app.models.gkach_transaction import GkachTransaction
        from app.models.cart import CartItem
        from app.models.message import Message
        from app.models.ad_interactions import AdLike, AdStar, AdComment, AdRating
        from app.models.admin_settings import AdminSettings # Import AdminSettings
        from app.models.party import Party, PartyParticipant
        from app.models.konferans import KonferansRoom, KonferansRecording
        from app.models.mennem_trip import MennemTrip
        from app.models.app_installation import AppInstallation  # PWA tracking model
        # Import ecole_biblique models so their tables get created
        from ecole_biblique.models import EcoleUser, Course, EcoleStudent, Grade, AdmissionTest, AdmissionAnswer, Module, StudentModule, Payment, TermsAcceptance, AuditLog
        db.create_all()
        
        # Create admin user
        try:
            admin_user = User.query.filter_by(whatsapp='+50942882076').first()
            if not admin_user:
                admin_user = User(
                    whatsapp='+50942882076',
                    pseudo='+50942882076',
                    name='Admin',
                    auth_provider='whatsapp',
                    is_active=True,
                    is_admin=True
                )
                admin_user.set_password('StanGlory2Yah1986')
                db.session.add(admin_user)
                db.session.commit()
                admin_gkach = UserGkach.query.filter_by(user_whatsapp=admin_user.whatsapp).first()
                if not admin_gkach:
                    db.session.add(UserGkach(user_id=admin_user.id, user_whatsapp=admin_user.whatsapp, gkach_balance=0))
                    db.session.commit()
                app.logger.info("Admin user created: +50942882076")
            elif not admin_user.is_admin:
                admin_user.is_admin = True
                admin_user.pseudo = '+50942882076'
                admin_user.set_password('StanGlory2Yah1986')
                db.session.commit()
        except Exception as e:
            app.logger.warning(f"Could not create admin user: {e}")
            db.session.rollback()

        # Create test user for easy testing
        try:
            test_user = User.query.filter_by(whatsapp='+50912345678').first()
            if not test_user:
                # Check if pseudo 'testuser' exists, if yes, use a different one
                pseudo = 'testuser'
                count = 1
                while User.query.filter_by(pseudo=pseudo).first():
                    pseudo = f'testuser{count}'
                    count += 1
                
                test_user = User(
                    whatsapp='+50912345678',
                    pseudo=pseudo,
                    name='Test User',
                    auth_provider='whatsapp',
                    is_active=True
                )
                test_user.set_password('123456')
                db.session.add(test_user)
                db.session.commit()
                
                # Create GKACH account for test user if not exists
                test_gkach = UserGkach.query.filter_by(user_whatsapp=test_user.whatsapp).first()
                if not test_gkach:
                    test_gkach = UserGkach(
                        user_id=test_user.id,
                        user_whatsapp=test_user.whatsapp,
                        gkach_balance=1000
                    )
                    db.session.add(test_gkach)
                    db.session.commit()
                app.logger.info("Test user created: +50912345678 / 123456")
        except Exception as e:
            app.logger.warning(f"Could not create test user: {e}")
            db.session.rollback()
    
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


def register_error_handlers(app):
    """Register error handlers"""
    
    @app.errorhandler(404)
    def not_found(e):
        return render_template('error.html'), 404
    
    @app.errorhandler(500)
    def internal_error(e):
        return render_template('error.html'), 500


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
    """Setup application logging"""
    try:
        if not os.path.exists('logs'):
            os.makedirs('logs', exist_ok=True)
        
        log_level = getattr(logging, app.config.get('LOG_LEVEL', 'INFO'))
        file_handler = logging.FileHandler('logs/glory2yahpub.log')
        file_handler.setLevel(log_level)
        
        app.logger.addHandler(file_handler)
        app.logger.setLevel(log_level)
    except Exception as e:
        # If file logging fails, just use stdout
        pass


# Gunicorn entrypoint compatibility:
# Procfile runs `gunicorn app:app ...` which expects an attribute named `app`
# in this module. Provide it using the application factory.
app = create_app(os.environ.get('FLASK_ENV', 'development'))
