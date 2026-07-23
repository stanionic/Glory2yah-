"""
PWA Routes Blueprint
Progressive Web App configuration, manifest, service worker, and analytics
"""
import os
import json
from flask import Blueprint, render_template, jsonify, request, current_app, send_from_directory
from app import db
from app.models.app_installation import AppInstallation
from app.models.admin_settings import AdminSettings

pwa_bp = Blueprint('pwa', __name__, url_prefix='/pwa')


@pwa_bp.route('/manifest.json')
def serve_manifest():
    """Serve the PWA manifest.json with dynamic configuration"""
    return send_from_directory(
        os.path.join(current_app.root_path, '..', 'static'),
        'manifest.json',
        mimetype='application/json'
    )


@pwa_bp.route('/sw.js')
def serve_sw():
    """Serve the service worker with correct MIME type"""
    response = send_from_directory(
        os.path.join(current_app.root_path, '..', 'static'),
        'sw.js',
        mimetype='application/javascript'
    )
    # Service worker must not be cached
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    response.headers['Service-Worker-Allowed'] = '/'
    return response


@pwa_bp.route('/api/analytics', methods=['POST'])
def analytics():
    """
    Receive PWA install analytics from client-side
    Expects JSON: { user_id, device_type, browser, os, language, 
                    install_prompt_displayed, install_completed, dismissed }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400
        
        # Record the installation event
        record = AppInstallation.record_event(
            user_id=data.get('user_id'),
            device_type=data.get('device_type', 'desktop'),
            browser=data.get('browser', 'unknown'),
            os=data.get('os', 'unknown'),
            language=data.get('language', 'ht'),
            install_prompt_displayed=data.get('install_prompt_displayed', False),
            install_completed=data.get('install_completed', False),
            dismissed=data.get('dismissed', False)
        )
        
        return jsonify({
            'success': True,
            'record_id': record.id
        })
    except Exception as e:
        current_app.logger.error(f"PWA analytics error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@pwa_bp.route('/api/settings', methods=['GET'])
def get_settings():
    """
    Get PWA configuration settings for the client-side install prompt.
    These are managed via Admin SEVIS -> Configuration Application Mobile.
    """
    settings = {
        'pwa_enabled': AdminSettings.get_setting('pwa_enabled', 'True') == 'True',
        'popup_title': AdminSettings.get_setting('pwa_popup_title', 'Installer Glory2YahPub'),
        'popup_description': AdminSettings.get_setting('pwa_popup_description', 
            'Accédez rapidement aux boutiques, publications, annonces et services depuis votre téléphone.'),
        'popup_button_text': AdminSettings.get_setting('pwa_popup_button_text', 'Installer maintenant'),
        'popup_delay_seconds': int(AdminSettings.get_setting('pwa_popup_delay_seconds', '5')),
        'ios_guide_enabled': AdminSettings.get_setting('pwa_ios_guide_enabled', 'True') == 'True'
    }
    return jsonify(settings)


@pwa_bp.route('/api/settings', methods=['POST'])
def update_settings():
    """
    Update PWA configuration settings (admin only - should be protected).
    Called from Admin SEVIS.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400
        
        # Map of allowed settings
        allowed_settings = {
            'pwa_enabled': 'pwa_enabled',
            'popup_title': 'pwa_popup_title',
            'popup_description': 'pwa_popup_description',
            'popup_button_text': 'pwa_popup_button_text',
            'popup_delay_seconds': 'pwa_popup_delay_seconds',
            'ios_guide_enabled': 'pwa_ios_guide_enabled'
        }
        
        for key, setting_name in allowed_settings.items():
            if key in data:
                AdminSettings.set_setting(setting_name, data[key])
        
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.error(f"PWA settings update error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@pwa_bp.route('/api/stats', methods=['GET'])
def get_stats():
    """
    Get PWA installation statistics for Admin SEVIS dashboard.
    Returns: total_visitors, prompts_displayed, installs_completed, 
             dismissed, conversion_rate
    """
    stats = AppInstallation.get_stats()
    return jsonify(stats)


@pwa_bp.route('/api/events', methods=['GET'])
def get_events():
    """
    Get recent PWA installation events for admin view.
    """
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    query = AppInstallation.query.order_by(AppInstallation.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({
        'events': [event.to_dict() for event in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'current_page': page
    })


@pwa_bp.route('/offline')
def offline():
    """Serve the offline fallback page"""
    return render_template('offline.html')
