"""
G-Forms Blueprint
Serves the Glory2YahPub Forms React application
"""
import os
from flask import Blueprint, render_template, send_from_directory, current_app

gforms_bp = Blueprint('gforms', __name__, url_prefix='/forms')

# Path to the G-Forms React app
GFORMS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'G-Forms')
DIST_DIR = os.path.join(GFORMS_DIR, 'dist')


@gforms_bp.route('/')
def index():
    """Serve the G-Forms React app"""
    # If built, serve the dist folder
    if os.path.exists(os.path.join(DIST_DIR, 'index.html')):
        return send_from_directory(DIST_DIR, 'index.html')
    # Otherwise, serve a placeholder page
    return render_template('gforms/index.html')


@gforms_bp.route('/<path:filename>')
def serve_static(filename):
    """Serve static files from the G-Forms dist folder"""
    file_path = os.path.join(DIST_DIR, filename)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return send_from_directory(DIST_DIR, filename)
    # SPA fallback - serve index.html for client-side routes
    if os.path.exists(os.path.join(DIST_DIR, 'index.html')):
        return send_from_directory(DIST_DIR, 'index.html')
    return "Not found", 404