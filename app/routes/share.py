"""
Share Routes Blueprint
Viral sharing and rewards tracking
"""
from flask import Blueprint, redirect, request, url_for, current_app
from app.services.gkach_service import GkachService


share_bp = Blueprint('share', __name__)


@share_bp.route('/create', methods=['GET', 'POST'])
def create():
    """Create new ad/post"""
    from flask import render_template, flash, redirect
    from flask_login import login_required, current_user
    
    # For now, redirect to submit_ad or show a simple form
    # This will be fully implemented in the next phase
    flash('Fonksyon sa ap vini byento!', 'info')
    return redirect(url_for('main.index'))


@share_bp.route('/b/<batch_id>')
def batch_click(batch_id):
    """Handle click on a shared batch link"""
    from flask import redirect, url_for
    referrer = request.args.get('r')  # Referrer WhatsApp
    
    if referrer:
        try:
            GkachService.track_batch_click(batch_id, referrer)
        except Exception as e:
            current_app.logger.error(f"Error tracking click: {e}")
            
    # Always redirect to main.index - preserves batch_id in URL for analytics
    return redirect(url_for('main.index', batch=batch_id))
