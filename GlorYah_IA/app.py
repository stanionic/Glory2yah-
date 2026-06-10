#!/usr/bin/env python3
"""
MANDEMMAPBAW - Multimodal AI Chatbot
Application principale Flask - Version améliorée
"""

import os
import json
import secrets
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_file, session
from flask_cors import CORS
from werkzeug.utils import secure_filename
import logging

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialisation de Flask
app = Flask(__name__)
CORS(app)

# Configuration de l'application
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', 
    'sqlite:///mandemmapbaw.db'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = 'static/generated'

# Création des dossiers nécessaires
REQUIRED_DIRS = [
    'static/generated/images',
    'static/generated/videos',
    'models',
    'database'
]

for directory in REQUIRED_DIRS:
    Path(directory).mkdir(parents=True, exist_ok=True)
    logger.info(f"Directory ensured: {directory}")

# Import de la base de données et des modèles
from database.models import db, ChatHistory, ImageGeneration, VideoGeneration, CodeGeneration

# Initialisation de la base de données avec l'app
db.init_app(app)

# Import des générateurs AI avec lazy loading
class AIGenerators:
    """Lazy loading pour les générateurs AI"""
    _text_gen = None
    _image_gen = None
    _video_gen = None
    _code_gen = None
    
    @property
    def text_gen(self):
        if self._text_gen is None:
            from models.text_generator import TextGenerator
            self._text_gen = TextGenerator()
            logger.info("Text generator loaded")
        return self._text_gen
    
    @property
    def image_gen(self):
        if self._image_gen is None:
            from models.image_generator import ImageGenerator
            self._image_gen = ImageGenerator()
            logger.info("Image generator loaded")
        return self._image_gen
    
    @property
    def video_gen(self):
        if self._video_gen is None:
            from models.video_generator import VideoGenerator
            self._video_gen = VideoGenerator()
            logger.info("Video generator loaded")
        return self._video_gen
    
    @property
    def code_gen(self):
        if self._code_gen is None:
            from models.code_generator import CodeGenerator
            self._code_gen = CodeGenerator()
            logger.info("Code generator loaded")
        return self._code_gen

generators = AIGenerators()

# =============================================================================
# Routes principales
# =============================================================================

@app.route('/')
def index():
    """Page d'accueil avec le chat"""
    return render_template('index.html', 
                         title='MANDEMMAPBAW',
                         slogan='Mande m map baw')

@app.route('/chat', methods=['POST'])
def chat():
    """Génération de texte via AI avec recherche web"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'Ou dwe ekri yon mesaj'}), 400

        prompt = data.get('prompt', '').strip()
        mode = data.get('mode', 'chat')
        use_web_search = data.get('web_search', False)  # NEW: Web search option

        if not prompt:
            return jsonify({'error': 'Ou dwe ekri yon mesaj'}), 400

        if len(prompt) > 5000:
            return jsonify({'error': 'Mesaj la two long (maksimòm 5000 karaktè)'}), 400

        # Génération de la réponse
        try:
            if mode == 'code':
                response = generators.code_gen.generate(prompt)
            else:
                # Pass web_search flag to generator
                response = generators.text_gen.generate(prompt, use_web_search=use_web_search)
        except Exception as gen_error:
            logger.error(f"Generation error: {gen_error}")
            response = "Mwen regrete, mwen gen yon pwoblèm. Tanpri eseye ankò."

        # Sauvegarde dans l'historique
        try:
            chat_entry = ChatHistory(
                prompt=prompt,
                response=response,
                mode=mode,
                timestamp=datetime.now()
            )
            db.session.add(chat_entry)
            db.session.commit()
        except Exception as db_error:
            logger.error(f"Database error: {db_error}")
            db.session.rollback()

        return jsonify({
            'success': True,
            'response': response,
            'timestamp': datetime.now().strftime('%H:%M'),
            'web_search_used': use_web_search  # NEW: Indicate if web search was used
        })

    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        return jsonify({'error': f'Erè: {str(e)}'}), 500

@app.route('/generate-image', methods=['POST'])
def generate_image():
    """Génération d'image avec Stable Diffusion"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'Ou dwe dekri imaj ou vle kreye a'}), 400
        
        prompt = data.get('prompt', '').strip()
        
        if not prompt:
            return jsonify({'error': 'Ou dwe dekri imaj ou vle kreye a'}), 400
        
        if len(prompt) > 1000:
            return jsonify({'error': 'Deskripsyon an two long (maksimòm 1000 karaktè)'}), 400
        
        # Génération de l'image
        filename, filepath = generators.image_gen.generate(prompt)
        
        # Sauvegarde dans la base de données
        try:
            image_entry = ImageGeneration(
                prompt=prompt,
                filename=filename,
                filepath=filepath,
                timestamp=datetime.now()
            )
            db.session.add(image_entry)
            db.session.commit()
        except Exception as db_error:
            logger.error(f"Database error: {db_error}")
            db.session.rollback()
        
        return jsonify({
            'success': True,
            'image_url': f'/static/generated/images/{filename}',
            'filename': filename
        })
        
    except Exception as e:
        logger.error(f"Image generation error: {e}", exc_info=True)
        return jsonify({'error': f'Erè nan jenere imaj la: {str(e)}'}), 500

@app.route('/generate-video', methods=['POST'])
def generate_video():
    """Génération de vidéo"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'Ou dwe dekri videyo ou vle kreye a'}), 400
        
        prompt = data.get('prompt', '').strip()
        
        if not prompt:
            return jsonify({'error': 'Ou dwe dekri videyo ou vle kreye a'}), 400
        
        if len(prompt) > 1000:
            return jsonify({'error': 'Deskripsyon an two long (maksimòm 1000 karaktè)'}), 400
        
        # Génération de la vidéo
        filename, filepath = generators.video_gen.generate(prompt)
        
        # Sauvegarde dans la base de données
        try:
            video_entry = VideoGeneration(
                prompt=prompt,
                filename=filename,
                filepath=filepath,
                timestamp=datetime.now()
            )
            db.session.add(video_entry)
            db.session.commit()
        except Exception as db_error:
            logger.error(f"Database error: {db_error}")
            db.session.rollback()
        
        return jsonify({
            'success': True,
            'video_url': f'/static/generated/videos/{filename}',
            'filename': filename
        })
        
    except Exception as e:
        logger.error(f"Video generation error: {e}", exc_info=True)
        return jsonify({'error': f'Erè nan jenere videyo a: {str(e)}'}), 500

@app.route('/download/<file_type>/<filename>')
def download_file(file_type, filename):
    """Téléchargement des fichiers générés"""
    try:
        # Sécurisation du nom de fichier
        filename = secure_filename(filename)
        
        if file_type == 'image':
            filepath = Path('static/generated/images') / filename
        elif file_type == 'video':
            filepath = Path('static/generated/videos') / filename
        else:
            return jsonify({'error': 'Kalite dosye pa bon'}), 400
        
        if not filepath.exists():
            return jsonify({'error': 'Dosye a pa egziste'}), 404
        
        return send_file(str(filepath), as_attachment=True)
        
    except Exception as e:
        logger.error(f"Download error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 404

@app.route('/history')
def get_history():
    """Récupération de l'historique"""
    try:
        mode = request.args.get('mode', 'all')
        limit = min(int(request.args.get('limit', 50)), 100)
        
        if mode == 'chat':
            history = ChatHistory.query.order_by(
                ChatHistory.timestamp.desc()
            ).limit(limit).all()
        elif mode == 'image':
            history = ImageGeneration.query.order_by(
                ImageGeneration.timestamp.desc()
            ).limit(limit).all()
        elif mode == 'video':
            history = VideoGeneration.query.order_by(
                VideoGeneration.timestamp.desc()
            ).limit(limit).all()
        elif mode == 'code':
            history = ChatHistory.query.filter_by(mode='code').order_by(
                ChatHistory.timestamp.desc()
            ).limit(limit).all()
        else:
            return jsonify({'error': 'Mòd istwa pa bon'}), 400
        
        return jsonify({
            'success': True,
            'history': [item.to_dict() for item in history]
        })
        
    except Exception as e:
        logger.error(f"History error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

# =============================================================================
# Routes d'administration
# =============================================================================

@app.route('/admin')
def admin():
    """Panneau d'administration"""
    return render_template('admin.html')

@app.route('/admin/delete', methods=['POST'])
def delete_history():
    """Suppression de l'historique"""
    try:
        data = request.get_json()
        mode = data.get('mode', 'all')
        
        if mode == 'all':
            db.session.query(ChatHistory).delete()
            db.session.query(ImageGeneration).delete()
            db.session.query(VideoGeneration).delete()
        elif mode == 'chat':
            db.session.query(ChatHistory).delete()
        elif mode == 'images':
            db.session.query(ImageGeneration).delete()
        elif mode == 'videos':
            db.session.query(VideoGeneration).delete()
        else:
            return jsonify({'error': 'Mòd pa bon'}), 400
        
        db.session.commit()
        logger.info(f"History deleted: {mode}")
        
        return jsonify({'success': True, 'message': 'Istwa efase avèk siksè'})
        
    except Exception as e:
        logger.error(f"Delete error: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/admin/stats')
def get_stats():
    """Récupération des statistiques"""
    try:
        stats = {
            'total_chats': ChatHistory.query.count(),
            'total_images': ImageGeneration.query.count(),
            'total_videos': VideoGeneration.query.count(),
            'recent_chats': ChatHistory.query.filter(
                ChatHistory.timestamp >= datetime.now().date()
            ).count(),
            'disk_usage': {
                'images': sum(
                    f.stat().st_size for f in Path('static/generated/images').glob('*')
                    if f.is_file()
                ) / (1024 * 1024),
                'videos': sum(
                    f.stat().st_size for f in Path('static/generated/videos').glob('*')
                    if f.is_file()
                ) / (1024 * 1024)
            }
        }
        
        return jsonify({'success': True, 'stats': stats})
        
    except Exception as e:
        logger.error(f"Stats error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

# =============================================================================
# Error handlers
# =============================================================================

@app.errorhandler(404)
def not_found(error):
    """Page 404"""
    return jsonify({'error': 'Paj la pa egziste'}), 404

@app.errorhandler(500)
def internal_error(error):
    """Page 500"""
    db.session.rollback()
    logger.error(f"Internal error: {error}", exc_info=True)
    return jsonify({'error': 'Erè entèn nan sèvè a'}), 500

@app.errorhandler(413)
def too_large(error):
    """File too large"""
    return jsonify({'error': 'Dosye a two gwo (maksimòm 16MB)'}), 413

# =============================================================================
# Initialisation
# =============================================================================

def init_db():
    """Initialisation de la base de données"""
    with app.app_context():
        try:
            db.create_all()
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Database initialization error: {e}")
            raise

# =============================================================================
# Point d'entrée
# =============================================================================

if __name__ == '__main__':
    init_db()
    
    # Configuration for development/production
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    host = os.environ.get('FLASK_HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', os.environ.get('FLASK_PORT', 5000)))
    
    logger.info(f"Starting MANDEMMAPBAW on {host}:{port} (debug={debug_mode})")
    
    app.run(
        debug=debug_mode,
        host=host,
        port=port
    )
