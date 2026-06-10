#!/usr/bin/env python3
"""
MANDEMMAPBAW v3.0 - Robust Multimodal AI Chatbot
Complete rebuild with web search, training, and full CRUD
"""

import os
import json
import secrets
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for
from flask_cors import CORS
from werkzeug.utils import secure_filename
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('mandemmapbaw.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize Flask
app = Flask(__name__)
CORS(app)

# Configuration
app.config.update(
    SECRET_KEY=os.environ.get('SECRET_KEY', secrets.token_hex(32)),
    SQLALCHEMY_DATABASE_URI=os.environ.get('DATABASE_URL', 'sqlite:///mandemmapbaw.db'),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16MB
    UPLOAD_FOLDER='static/generated',
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=3600  # 1 hour
)

# Create required directories
REQUIRED_DIRS = [
    'static/generated/images',
    'static/generated/videos',
    'static/training/images',
    'static/training/videos',
    'models',
    'database'
]

for directory in REQUIRED_DIRS:
    Path(directory).mkdir(parents=True, exist_ok=True)

# Database initialization
from database.models import db, ChatHistory, ImageGeneration, VideoGeneration, CodeGeneration

db.init_app(app)

# Import training models
try:
    from database.training_models import TrainingImage, TrainingVideo, TrainingConversation, TrainingCode
    TRAINING_AVAILABLE = True
    logger.info("Training models loaded")
except ImportError as e:
    TRAINING_AVAILABLE = False
    logger.warning(f"Training models not available: {e}")

# Import admin authentication
try:
    from models.admin_auth import get_admin_auth, admin_required
    ADMIN_AUTH_AVAILABLE = True
    logger.info("Admin authentication loaded")
except ImportError as e:
    ADMIN_AUTH_AVAILABLE = False
    logger.warning(f"Admin auth not available: {e}")
    # Create dummy decorator if not available
    def admin_required(f):
        return f

# AI Generators
class AIGenerators:
    """Lazy-loaded AI generators"""
    
    def __init__(self):
        self._text_gen = None
        self._image_gen = None
        self._video_gen = None
        self._code_gen = None
        self._web_search = None
    
    @property
    def text_gen(self):
        if self._text_gen is None:
            from models.text_generator import get_text_generator
            self._text_gen = get_text_generator()
        return self._text_gen
    
    @property
    def image_gen(self):
        if self._image_gen is None:
            from models.image_generator import get_image_generator
            self._image_gen = get_image_generator()
        return self._image_gen
    
    @property
    def video_gen(self):
        if self._video_gen is None:
            from models.video_generator import get_video_generator
            self._video_gen = get_video_generator()
        return self._video_gen
    
    @property
    def code_gen(self):
        if self._code_gen is None:
            from models.code_generator import get_code_generator
            self._code_gen = get_code_generator()
        return self._code_gen
    
    @property
    def web_search(self):
        if self._web_search is None:
            from models.web_search import get_web_searcher
            self._web_search = get_web_searcher()
        return self._web_search

generators = AIGenerators()

# =============================================================================
# Helper Functions
# =============================================================================

def init_db():
    """Initialize database with all tables"""
    with app.app_context():
        try:
            db.create_all()
            logger.info("Database initialized successfully")
            
            # Log table counts
            logger.info(f"ChatHistory: {ChatHistory.query.count()} entries")
            if TRAINING_AVAILABLE:
                logger.info(f"TrainingConversation: {TrainingConversation.query.count()} entries")
        except Exception as e:
            logger.error(f"Database initialization error: {e}")
            raise

def validate_input(data, required_fields):
    """Validate request data"""
    if not data:
        return False, "No data provided"
    
    for field in required_fields:
        if field not in data or not str(data[field]).strip():
            return False, f"Missing required field: {field}"
    
    return True, "Valid"

# =============================================================================
# Main Routes
# =============================================================================

@app.route('/')
def index():
    """Homepage"""
    return render_template('index.html')

@app.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'database': 'connected' if db else 'not connected',
        'training_available': TRAINING_AVAILABLE,
        'admin_auth': ADMIN_AUTH_AVAILABLE
    })

# =============================================================================
# Chat Routes (with Web Search Integration)
# =============================================================================

@app.route('/chat', methods=['POST'])
def chat():
    """Chat with AI - includes web search capability"""
    try:
        data = request.get_json()
        
        # Validate input
        valid, message = validate_input(data, ['prompt'])
        if not valid:
            return jsonify({'error': message, 'success': False}), 400
        
        prompt = data.get('prompt', '').strip()
        mode = data.get('mode', 'chat')
        enable_web_search = data.get('enable_web_search', True)
        
        # Length validation
        if len(prompt) > 5000:
            return jsonify({
                'error': 'Message too long (max 5000 characters)',
                'success': False
            }), 400
        
        logger.info(f"Chat request: mode={mode}, web_search={enable_web_search}")
        
        # Generate response
        response = None
        web_search_used = False
        
        try:
            if mode == 'code':
                response = generators.code_gen.generate(prompt)
            else:
                # Try web search first if enabled
                if enable_web_search and generators.web_search.should_search(prompt):
                    web_result = generators.web_search.search_and_summarize(prompt)
                    if web_result:
                        response = web_result
                        web_search_used = True
                        logger.info("Web search used successfully")
                
                # Fall back to text generation
                if not response:
                    response = generators.text_gen.generate(prompt, use_web_search=False)
        
        except Exception as gen_error:
            logger.error(f"Generation error: {gen_error}", exc_info=True)
            response = "Mwen regret, mwen gen yon pwoblèm. Tanpri eseye ankò."
        
        # Save to history
        try:
            chat_entry = ChatHistory(
                prompt=prompt,
                response=response,
                mode=mode,
                timestamp=datetime.now()
            )
            db.session.add(chat_entry)
            db.session.commit()
            logger.info(f"Chat saved to history: ID {chat_entry.id}")
        except Exception as db_error:
            logger.error(f"Database save error: {db_error}")
            db.session.rollback()
        
        return jsonify({
            'success': True,
            'response': response,
            'timestamp': datetime.now().strftime('%H:%M'),
            'web_search_used': web_search_used
        })
        
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        return jsonify({
            'error': f'Server error: {str(e)}',
            'success': False
        }), 500

@app.route('/generate-image', methods=['POST'])
def generate_image():
    """Generate image from text"""
    try:
        data = request.get_json()
        
        valid, message = validate_input(data, ['prompt'])
        if not valid:
            return jsonify({'error': message, 'success': False}), 400
        
        prompt = data['prompt'].strip()
        
        logger.info(f"Image generation request: {prompt[:50]}...")
        
        # Generate image
        image_path = generators.image_gen.generate(prompt)
        
        if not image_path:
            return jsonify({
                'error': 'Image generation failed',
                'success': False
            }), 500
        
        # Save to database
        try:
            img_entry = ImageGeneration(
                prompt=prompt,
                image_path=image_path,
                timestamp=datetime.now()
            )
            db.session.add(img_entry)
            db.session.commit()
        except Exception as db_error:
            logger.error(f"Database save error: {db_error}")
            db.session.rollback()
        
        return jsonify({
            'success': True,
            'image_url': f'/{image_path}',
            'timestamp': datetime.now().strftime('%H:%M')
        })
        
    except Exception as e:
        logger.error(f"Image generation error: {e}", exc_info=True)
        return jsonify({
            'error': f'Image generation error: {str(e)}',
            'success': False
        }), 500

@app.route('/generate-video', methods=['POST'])
def generate_video():
    """Generate video animation"""
    try:
        data = request.get_json()
        
        valid, message = validate_input(data, ['prompt'])
        if not valid:
            return jsonify({'error': message, 'success': False}), 400
        
        prompt = data['prompt'].strip()
        animation_type = data.get('animation_type', 'wave')
        
        logger.info(f"Video generation: {prompt[:50]}... type={animation_type}")
        
        # Generate video
        video_path = generators.video_gen.generate(prompt, animation_type)
        
        if not video_path:
            return jsonify({
                'error': 'Video generation failed',
                'success': False
            }), 500
        
        # Save to database
        try:
            video_entry = VideoGeneration(
                prompt=prompt,
                video_path=video_path,
                animation_type=animation_type,
                timestamp=datetime.now()
            )
            db.session.add(video_entry)
            db.session.commit()
        except Exception as db_error:
            logger.error(f"Database save error: {db_error}")
            db.session.rollback()
        
        return jsonify({
            'success': True,
            'video_url': f'/{video_path}',
            'timestamp': datetime.now().strftime('%H:%M')
        })
        
    except Exception as e:
        logger.error(f"Video generation error: {e}", exc_info=True)
        return jsonify({
            'error': f'Video generation error: {str(e)}',
            'success': False
        }), 500

# =============================================================================
# Training System Routes
# =============================================================================

@app.route('/training')
def training_page():
    """Training interface"""
    return render_template('training.html')

@app.route('/training/stats')
def training_stats():
    """Get training statistics"""
    try:
        stats = {
            'total_images': 0,
            'total_videos': 0,
            'total_conversations': 0,
            'total_code': 0,
            'approved_conversations': 0,
            'approved_code': 0
        }
        
        if TRAINING_AVAILABLE:
            stats = {
                'total_images': TrainingImage.query.count(),
                'total_videos': TrainingVideo.query.count(),
                'total_conversations': TrainingConversation.query.count(),
                'total_code': TrainingCode.query.count(),
                'approved_conversations': TrainingConversation.query.filter_by(approved=True).count(),
                'approved_code': TrainingCode.query.filter_by(approved=True).count(),
            }
        
        return jsonify({'success': True, 'stats': stats})
    except Exception as e:
        logger.error(f"Training stats error: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'stats': {
                'total_images': 0,
                'total_videos': 0,
                'total_conversations': 0,
                'total_code': 0
            }
        })

@app.route('/training/submit-conversation', methods=['POST'])
def submit_training_conversation():
    """Submit conversation training example"""
    if not TRAINING_AVAILABLE:
        return jsonify({
            'error': 'Training system not available',
            'success': False
        }), 503
    
    try:
        data = request.get_json()
        
        valid, message = validate_input(data, ['user_message', 'expected_response'])
        if not valid:
            return jsonify({'error': message, 'success': False}), 400
        
        user_message = data['user_message'].strip()
        expected_response = data['expected_response'].strip()
        category = data.get('category', 'general')
        language = data.get('language', 'kreyol')
        
        # Create training entry
        training_conv = TrainingConversation(
            user_message=user_message,
            expected_response=expected_response,
            category=category,
            language=language,
            approved=False
        )
        
        db.session.add(training_conv)
        db.session.commit()
        
        logger.info(f"Training conversation submitted: ID {training_conv.id}")
        
        return jsonify({
            'success': True,
            'message': 'Konvèsasyon soumèt avèk siksè!',
            'id': training_conv.id
        })
        
    except Exception as e:
        logger.error(f"Submit conversation error: {e}")
        db.session.rollback()
        return jsonify({
            'error': f'Error: {str(e)}',
            'success': False
        }), 500

@app.route('/training/submit-code', methods=['POST'])
def submit_training_code():
    """Submit code training example"""
    if not TRAINING_AVAILABLE:
        return jsonify({
            'error': 'Training system not available',
            'success': False
        }), 503
    
    try:
        data = request.get_json()
        
        valid, message = validate_input(data, ['prompt', 'code'])
        if not valid:
            return jsonify({'error': message, 'success': False}), 400
        
        prompt = data['prompt'].strip()
        code = data['code'].strip()
        language = data.get('language', 'python')
        description = data.get('description', '').strip()
        
        # Create training entry
        training_code = TrainingCode(
            prompt=prompt,
            code=code,
            language=language,
            description=description,
            approved=False
        )
        
        db.session.add(training_code)
        db.session.commit()
        
        logger.info(f"Training code submitted: ID {training_code.id}")
        
        return jsonify({
            'success': True,
            'message': 'Kòd soumèt avèk siksè!',
            'id': training_code.id
        })
        
    except Exception as e:
        logger.error(f"Submit code error: {e}")
        db.session.rollback()
        return jsonify({
            'error': f'Error: {str(e)}',
            'success': False
        }), 500

# =============================================================================
# Admin Authentication Routes
# =============================================================================

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin login"""
    if not ADMIN_AUTH_AVAILABLE:
        return jsonify({'error': 'Admin auth not available'}), 503
    
    if request.method == 'GET':
        return render_template('admin_login.html')
    
    try:
        data = request.get_json()
        
        valid, message = validate_input(data, ['username', 'password'])
        if not valid:
            return jsonify({'error': message, 'success': False}), 400
        
        username = data['username'].strip()
        password = data['password'].strip()
        
        auth = get_admin_auth()
        if auth.login(username, password):
            logger.info(f"Admin login successful: {username}")
            return jsonify({
                'success': True,
                'message': 'Login successful'
            })
        else:
            logger.warning(f"Failed login attempt: {username}")
            return jsonify({
                'success': False,
                'error': 'Invalid credentials'
            }), 401
            
    except Exception as e:
        logger.error(f"Login error: {e}")
        return jsonify({
            'success': False,
            'error': 'Login error'
        }), 500

@app.route('/admin/logout')
def admin_logout():
    """Logout admin"""
    if ADMIN_AUTH_AVAILABLE:
        auth = get_admin_auth()
        auth.logout()
    return redirect(url_for('index'))

# =============================================================================
# Admin Panel - Full CRUD Operations
# =============================================================================

@app.route('/admin')
@admin_required
def admin_panel():
    """Admin dashboard"""
    try:
        # Get admin info
        admin_username = 'Admin'
        if ADMIN_AUTH_AVAILABLE:
            auth = get_admin_auth()
            admin_username = auth.get_username() or 'Admin'
        
        # Get statistics
        stats = {
            'total_chats': ChatHistory.query.count(),
            'total_images': ImageGeneration.query.count(),
            'total_videos': VideoGeneration.query.count(),
            'total_code': CodeGeneration.query.count(),
        }
        
        # Get training stats
        if TRAINING_AVAILABLE:
            stats.update({
                'pending_conversations': TrainingConversation.query.filter_by(approved=False).count(),
                'approved_conversations': TrainingConversation.query.filter_by(approved=True).count(),
                'pending_code': TrainingCode.query.filter_by(approved=False).count(),
                'approved_code': TrainingCode.query.filter_by(approved=True).count(),
            })
        
        # Get recent activity
        recent_chats = ChatHistory.query.order_by(
            ChatHistory.timestamp.desc()
        ).limit(10).all()
        
        return render_template('admin.html',
            admin_username=admin_username,
            stats=stats,
            recent_chats=recent_chats
        )
        
    except Exception as e:
        logger.error(f"Admin panel error: {e}")
        return jsonify({'error': str(e)}), 500

# CRUD: Read - Get all items
@app.route('/admin/chats')
@admin_required
def admin_get_chats():
    """Get all chat history"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        
        chats = ChatHistory.query.order_by(
            ChatHistory.timestamp.desc()
        ).paginate(page=page, per_page=per_page, error_out=False)
        
        return jsonify({
            'success': True,
            'chats': [
                {
                    'id': chat.id,
                    'prompt': chat.prompt,
                    'response': chat.response,
                    'mode': chat.mode,
                    'timestamp': chat.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                }
                for chat in chats.items
            ],
            'total': chats.total,
            'pages': chats.pages,
            'current_page': chats.page
        })
    except Exception as e:
        logger.error(f"Get chats error: {e}")
        return jsonify({'error': str(e), 'success': False}), 500

# CRUD: Read - Get single item
@app.route('/admin/chat/<int:chat_id>')
@admin_required
def admin_get_chat(chat_id):
    """Get single chat"""
    try:
        chat = ChatHistory.query.get_or_404(chat_id)
        return jsonify({
            'success': True,
            'chat': {
                'id': chat.id,
                'prompt': chat.prompt,
                'response': chat.response,
                'mode': chat.mode,
                'timestamp': chat.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            }
        })
    except Exception as e:
        logger.error(f"Get chat error: {e}")
        return jsonify({'error': str(e), 'success': False}), 404

# CRUD: Update
@app.route('/admin/chat/<int:chat_id>', methods=['PUT'])
@admin_required
def admin_update_chat(chat_id):
    """Update chat entry"""
    try:
        chat = ChatHistory.query.get_or_404(chat_id)
        data = request.get_json()
        
        if 'prompt' in data:
            chat.prompt = data['prompt']
        if 'response' in data:
            chat.response = data['response']
        if 'mode' in data:
            chat.mode = data['mode']
        
        db.session.commit()
        logger.info(f"Chat updated: ID {chat_id}")
        
        return jsonify({
            'success': True,
            'message': 'Chat updated successfully'
        })
    except Exception as e:
        logger.error(f"Update chat error: {e}")
        db.session.rollback()
        return jsonify({'error': str(e), 'success': False}), 500

# CRUD: Delete
@app.route('/admin/chat/<int:chat_id>', methods=['DELETE'])
@admin_required
def admin_delete_chat(chat_id):
    """Delete chat entry"""
    try:
        chat = ChatHistory.query.get_or_404(chat_id)
        db.session.delete(chat)
        db.session.commit()
        logger.info(f"Chat deleted: ID {chat_id}")
        
        return jsonify({
            'success': True,
            'message': 'Chat deleted successfully'
        })
    except Exception as e:
        logger.error(f"Delete chat error: {e}")
        db.session.rollback()
        return jsonify({'error': str(e), 'success': False}), 500

# CRUD: Bulk Delete
@app.route('/admin/chats/bulk-delete', methods=['POST'])
@admin_required
def admin_bulk_delete_chats():
    """Bulk delete chats"""
    try:
        data = request.get_json()
        chat_ids = data.get('ids', [])
        
        if not chat_ids:
            return jsonify({'error': 'No IDs provided', 'success': False}), 400
        
        deleted = ChatHistory.query.filter(ChatHistory.id.in_(chat_ids)).delete(synchronize_session=False)
        db.session.commit()
        
        logger.info(f"Bulk delete: {deleted} chats deleted")
        
        return jsonify({
            'success': True,
            'message': f'{deleted} chats deleted',
            'deleted_count': deleted
        })
    except Exception as e:
        logger.error(f"Bulk delete error: {e}")
        db.session.rollback()
        return jsonify({'error': str(e), 'success': False}), 500

# Training CRUD - Approve
@app.route('/admin/training/approve/<model_type>/<int:item_id>', methods=['POST'])
@admin_required
def admin_approve_training(model_type, item_id):
    """Approve training item"""
    if not TRAINING_AVAILABLE:
        return jsonify({'error': 'Training not available', 'success': False}), 503
    
    try:
        model_map = {
            'conversation': TrainingConversation,
            'code': TrainingCode
        }
        
        if model_type not in model_map:
            return jsonify({'error': 'Invalid type', 'success': False}), 400
        
        item = model_map[model_type].query.get_or_404(item_id)
        item.approved = True
        db.session.commit()
        
        # Reload training if conversation
        if model_type == 'conversation':
            from models.smart_fallback import get_smart_fallback
            fallback = get_smart_fallback()
            fallback._load_user_training()
        
        logger.info(f"Approved {model_type} ID {item_id}")
        
        return jsonify({
            'success': True,
            'message': 'Approved successfully'
        })
    except Exception as e:
        logger.error(f"Approve error: {e}")
        db.session.rollback()
        return jsonify({'error': str(e), 'success': False}), 500

# Training CRUD - Delete
@app.route('/admin/training/<model_type>/<int:item_id>', methods=['DELETE'])
@admin_required
def admin_delete_training(model_type, item_id):
    """Delete training item"""
    if not TRAINING_AVAILABLE:
        return jsonify({'error': 'Training not available', 'success': False}), 503
    
    try:
        model_map = {
            'conversation': TrainingConversation,
            'code': TrainingCode
        }
        
        if model_type not in model_map:
            return jsonify({'error': 'Invalid type', 'success': False}), 400
        
        item = model_map[model_type].query.get_or_404(item_id)
        db.session.delete(item)
        db.session.commit()
        
        logger.info(f"Deleted {model_type} ID {item_id}")
        
        return jsonify({
            'success': True,
            'message': 'Deleted successfully'
        })
    except Exception as e:
        logger.error(f"Delete training error: {e}")
        db.session.rollback()
        return jsonify({'error': str(e), 'success': False}), 500

# Training CRUD - List
@app.route('/admin/training/<model_type>')
@admin_required
def admin_list_training(model_type):
    """List training items"""
    if not TRAINING_AVAILABLE:
        return jsonify({'error': 'Training not available', 'success': False}), 503
    
    try:
        model_map = {
            'conversation': TrainingConversation,
            'code': TrainingCode
        }
        
        if model_type not in model_map:
            return jsonify({'error': 'Invalid type', 'success': False}), 400
        
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        approved = request.args.get('approved', None)
        
        query = model_map[model_type].query
        
        if approved is not None:
            query = query.filter_by(approved=(approved.lower() == 'true'))
        
        items = query.order_by(model_map[model_type].timestamp.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        return jsonify({
            'success': True,
            'items': [item.to_dict() for item in items.items],
            'total': items.total,
            'pages': items.pages,
            'current_page': items.page
        })
    except Exception as e:
        logger.error(f"List training error: {e}")
        return jsonify({'error': str(e), 'success': False}), 500

# =============================================================================
# Error Handlers
# =============================================================================

@app.errorhandler(404)
def not_found(error):
    """404 handler"""
    return jsonify({'error': 'Not found', 'success': False}), 404

@app.errorhandler(500)
def internal_error(error):
    """500 handler"""
    logger.error(f"Internal error: {error}")
    db.session.rollback()
    return jsonify({'error': 'Internal server error', 'success': False}), 500

# =============================================================================
# Initialization
# =============================================================================

if __name__ == '__main__':
    # Initialize database
    init_db()
    
    # Configuration
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    host = os.environ.get('FLASK_HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', os.environ.get('FLASK_PORT', 5000)))
    
    logger.info(f"Starting MANDEMMAPBAW v3.0 on {host}:{port} (debug={debug_mode})")
    
    # Run app
    app.run(
        debug=debug_mode,
        host=host,
        port=port
    )
