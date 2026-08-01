"""
PWA Routes Blueprint
Progressive Web App configuration, manifest, service worker, and analytics
"""
import os
import json
from flask import Blueprint, render_template, jsonify, request, current_app, send_from_directory
from flask_login import login_required, current_user
from app import db
from app.models.app_installation import AppInstallation
from app.models.admin_settings import AdminSettings
from app.utils.security import admin_required

pwa_bp = Blueprint('pwa', __name__, url_prefix='/pwa')


@pwa_bp.route('/manifest.json')
def serve_manifest():
    return send_from_directory(
        os.path.join(current_app.root_path, '..', 'static'),
        'manifest.json',
        mimetype='application/json'
    )


@pwa_bp.route('/sw.js')
def serve_sw():
    response = send_from_directory(
        os.path.join(current_app.root_path, '..', 'static'),
        'sw.js',
        mimetype='application/javascript'
    )
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    response.headers['Service-Worker-Allowed'] = '/'
    return response


@pwa_bp.route('/api/analytics', methods=['POST'])
def analytics():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400
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
        return jsonify({'success': False, 'message': 'Erè nan anrejistreman done analiz PWA a.'}), 500


@pwa_bp.route('/api/settings', methods=['GET'])
def get_settings():
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
@login_required
@admin_required
def update_settings():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400
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
        return jsonify({'success': False, 'message': 'Erè nan mete ajou paramèt PWA yo.'}), 500


@pwa_bp.route('/api/stats', methods=['GET'])
@login_required
@admin_required
def get_stats():
    stats = AppInstallation.get_stats()
    return jsonify(stats)


@pwa_bp.route('/api/events', methods=['GET'])
@login_required
@admin_required
def get_events():
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
    return render_template('offline.html')
