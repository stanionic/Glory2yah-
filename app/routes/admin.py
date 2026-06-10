"""
Admin Routes Blueprint
Management of ads, users, batches, and transactions
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.services.ad_service import AdService
from app.services.gkach_service import GkachService
from app.utils.security import admin_required


admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/')
@login_required
@admin_required
def dashboard():
    """Admin dashboard"""
    stats = AdService.get_stats()
    recent_ads = AdService.get_approved_ads(page=1, per_page=10)
    
    return render_template(
        'admin/dashboard.html',
        stats=stats,
        recent_ads=recent_ads,
        current_user=current_user
    )


@admin_bp.route('/ads')
@login_required
@admin_required
def manage_ads():
    """Manage all ads"""
    page = request.args.get('page', 1, type=int)
    ads = AdService.get_approved_ads(page=page, per_page=20)
    
    return render_template(
        'admin/ads.html',
        ads=ads,
        current_user=current_user
    )


@admin_bp.route('/ad/<ad_id>')
@login_required
@admin_required
def ad_detail(ad_id):
    """View individual ad details"""
    try:
        from app.services.ad_service import AdService
        ad = AdService.get_ad(ad_id)
        AdService.increment_views(ad_id)
    except Exception as e:
        flash(f'Ad not found: {str(e)}', 'error')
        return redirect(url_for('admin.manage_ads'))
    
    return render_template(
        'admin/ad_detail.html',
        ad=ad,
        current_user=current_user
    )


@admin_bp.route('/ads/approve/<ad_id>', methods=['POST'])
@login_required
@admin_required
def approve_ad(ad_id):
    """Approve an ad"""
    try:
        AdService.approve_ad(ad_id)
        flash('Piblisite apwouve!', 'success')
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


@admin_bp.route('/ads/reject/<ad_id>', methods=['POST'])
@login_required
@admin_required
def reject_ad(ad_id):
    """Reject an ad"""
    try:
        reason = request.form.get('reason', '')
        AdService.reject_ad(ad_id, reason)
        flash('Piblisite rejete.', 'info')
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


@admin_bp.route('/gkach/manage')
@login_required
@admin_required
def manage_gkach():
    """Manage user Gkach balances and requests"""
    # Logic to fetch Gkach requests and user balances
    return render_template('admin/gkach.html')


@admin_bp.route('/batches/create', methods=['POST'])
@login_required
@admin_required
def create_batch():
    """Create a new ad batch for viral sharing"""
    # Logic to create batch from approved ads
    flash('Nouvo pakèt piblisite kreye!', 'success')
    return redirect(url_for('admin.dashboard'))
