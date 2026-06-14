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

    # Ensure SECRET_KEY exists before CSRF token generation / CSRFProtect init.
    # Never hardcode secrets. On production/staging we fail fast with a clear error.
    secret_key = app.config.get("SECRET_KEY")
    if not secret_key:
        # Allow local development to boot with a generated SECRET_KEY and keep CSRF enabled.
        # CSRF must remain enabled in non-local environments.
        if str(config_name).lower() in ("development", "local", "dev"):
            import secrets
            secret_key = secrets.token_hex(32)
            app.config["SECRET_KEY"] = secret_key
            app.secret_key = secret_key
            app.logger.warning("SECRET_KEY not set. Generated temporary SECRET_KEY for development (CSRF remains enabled).")
        else:
            raise RuntimeError(
                "SECRET_KEY is required for CSRF protection but was not found. "
                "Set the 'SECRET_KEY' environment variable on Render."
            )
    else:
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
    
    @login_manager.user_loader
    def load_user(user_id):
        from app.models.user import User
        return User.query.get(int(user_id))
    
    @app.context_processor
    def inject_global_data():
        from flask_login import current_user
        from app.services.cart_service import CartService
        
        data = {
            'is_logged_in': current_user.is_authenticated,
            'cart_count': 0
        }
        
        if current_user.is_authenticated:
            try:
                cart_totals = CartService.calculate_totals(current_user.id)
                data['cart_count'] = cart_totals['count']
            except:
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
        db.create_all()
    
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
    
    # Register old blueprints
    try:
        from konferans.routes import konferans_bp, register_socketio_handlers
        app.register_blueprint(konferans_bp, url_prefix='/konferans')
        register_socketio_handlers(socketio)
    except:
        pass
    
    try:
        from ecole_biblique.app import ecole_biblique_bp
        app.register_blueprint(ecole_biblique_bp, url_prefix='/ecole_biblique')
    except:
        pass
    
    try:
        from party.app import party_bp
        app.register_blueprint(party_bp, url_prefix='/fet')
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
