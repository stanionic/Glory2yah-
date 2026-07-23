"""
Admin Routes Blueprint
Management of ads, users, batches, and transactions
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_required, current_user
from app import db
import uuid
from datetime import datetime
from app.services.ad_service import AdService, Ad
from app.services.gkach_service import GkachService
from app.models.user import User
from app.models.user_gkach import UserGkach
from app.models.gkach_transaction import GkachTransaction
from app.models.admin_settings import AdminSettings # Import AdminSettings
from app.utils.security import admin_required


admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/login', methods=['GET', 'POST'])
def admin_login():
    """Dedicated admin login page"""
    from flask_login import login_user, current_user
    if current_user.is_authenticated and current_user.is_admin:
        return redirect(url_for('admin.dashboard'))

    if request.method == 'POST':
        pseudo = request.form.get('pseudo', '').strip()
        password = request.form.get('password', '').strip()
        user = User.query.filter(
            db.or_(User.pseudo == pseudo, User.whatsapp == pseudo)
        ).first()
        if user and user.is_admin and user.check_password(password):
            login_user(user)
            flash('Byenveni Administratè!', 'success')
            return redirect(url_for('admin.dashboard'))
        flash('Pseudo oswa modpas envalid.', 'error')

    return render_template('admin_login.html')


@admin_bp.route('/')
@login_required
@admin_required
def dashboard():
    """Admin dashboard"""
    from app.models.ad import Ad
    from app.models.batch import Batch
    from app.models.user_gkach import UserGkach
    
    stats = AdService.get_stats()
    ads = Ad.query.all()  # Get all ads for review
    batches = Batch.query.all()
    users_gkach = UserGkach.query.all()
    
    # Fetch all admin settings
    admin_settings = AdminSettings.get_all_settings()
    
    return render_template(
        'admin.html',
        stats=stats,
        ads=ads,
        batches=batches,
        users_gkach=users_gkach,
        admin_settings=admin_settings,
        current_user=current_user
    )


@admin_bp.route('/users')
@login_required
@admin_required
def manage_users():
    """Manage all users"""
    users = User.query.all()
    return render_template(
        'admin_users.html',
        users=users,
        current_user=current_user
    )


@admin_bp.route('/users/<int:user_id>')
@login_required
@admin_required
def admin_view_user(user_id):
    """View individual user details"""
    user = User.query.get_or_404(user_id)
    user_gkach = UserGkach.query.filter_by(user_id=user.id).first()
    transactions = GkachTransaction.query.filter_by(user_whatsapp=user.whatsapp).all()
    user_ads = Ad.query.filter_by(user_whatsapp=user.whatsapp).all()
    gkach_balance = user_gkach.gkach_balance if user_gkach else 0
    
    return render_template(
        'admin_view_user.html',
        user=user,
        user_gkach=user_gkach,
        transactions=transactions,
        user_ads=user_ads,
        gkach_balance=gkach_balance,
        current_user=current_user
    )


@admin_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_edit_user(user_id):
    """Edit user details"""
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        user.pseudo = request.form.get('pseudo', user.pseudo)
        user.name = request.form.get('name', user.name)
        user.whatsapp = request.form.get('whatsapp', user.whatsapp)
        user.bio = request.form.get('bio', user.bio)
        user.is_active = request.form.get('is_active') == 'on'
        user.is_admin = request.form.get('is_admin') == 'on'
        
        db.session.commit()
        flash('Itilizatè modifye avèk siksè!', 'success')
        return redirect(url_for('admin.admin_view_user', user_id=user.id))
    
    return render_template(
        'admin_edit_user.html',
        user=user,
        current_user=current_user
    )


@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_user(user_id):
    """Delete a user"""
    if user_id == current_user.id:
        flash('Ou pa ka efase tèt ou menm!', 'error')
        return redirect(url_for('admin.manage_users'))
    
    user = User.query.get_or_404(user_id)
    UserGkach.query.filter_by(user_id=user.id).delete()
    db.session.delete(user)
    db.session.commit()
    flash('Itilizatè efase avèk siksè!', 'success')
    return redirect(url_for('admin.manage_users'))


@admin_bp.route('/ads')
@login_required
@admin_required
def manage_ads():
    """Manage all ads"""
    page = request.args.get('page', 1, type=int)
    ads = AdService.get_approved_ads(page=page, per_page=20)
    
    return render_template(
        'admin.html',
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
        'ad_detail.html',
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
    from app.utils.validators import sanitize_text, ValidationError

    """Reject an ad"""
    try:
        reason = sanitize_text(request.form.get('reason', ''))
        AdService.reject_ad(ad_id, reason)
        flash('Piblisite rejete.', 'info')
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


@admin_bp.route('/gkach/manage', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_gkach():
    """Manage user Gkach balances and requests"""
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'set_rate':
            # TODO: Implement exchange rate setting
            flash('Fonksyon rate ap vini byento!', 'info')
        elif action in ['approve_request', 'reject_request']:
            import json
            user_whatsapp = request.form.get('whatsapp')
            request_id = request.form.get('request_id')
            
            account = UserGkach.query.filter_by(user_whatsapp=user_whatsapp).first()
            if account and account.gkach_requests:
                requests_list = json.loads(account.gkach_requests)
                for req in requests_list:
                    if req['request_id'] == request_id:
                        if action == 'approve_request':
                            req['status'] = 'approved'
                            GkachService.add_balance(user_whatsapp, req['amount'], f"Demann apwouve: {req['amount']} Gkach")
                        else:
                            req['status'] = 'rejected'
                        break
                account.gkach_requests = json.dumps(requests_list)
                db.session.commit()
                flash('Demann traite avèk siksè!', 'success')
        elif action == 'edit_balance':
            user_whatsapp = request.form.get('whatsapp')
            new_balance = int(request.form.get('amount', 0))
            account = UserGkach.query.filter_by(user_whatsapp=user_whatsapp).first()
            if account:
                old_balance = account.gkach_balance
                account.gkach_balance = new_balance
                
                from app.models.gkach_transaction import GkachTransaction
                tx = GkachTransaction(
                    transaction_id=str(uuid.uuid4()),
                    user_whatsapp=user_whatsapp,
                    transaction_type='admin_edit',
                    amount=new_balance - old_balance,
                    old_balance=old_balance,
                    new_balance=new_balance,
                    description=f'Admin edit balance from {old_balance} to {new_balance}',
                    status='completed'
                )
                db.session.add(tx)
                
                from app.services.redis_service import RedisService
                from app import redis_client
                RedisService(redis_client).invalidate_gkach_balance(user_whatsapp)
                
                db.session.commit()
                flash('Balans modifye avèk siksè!', 'success')
        elif action == 'add_balance':
            user_whatsapp = request.form.get('whatsapp')
            add_amount = int(request.form.get('amount', 0))
            if add_amount > 0:
                GkachService.add_balance(user_whatsapp, add_amount, f'Admin added balance: {add_amount} Gkach', 'admin_credit')
                flash('Balans ajoute avèk siksè!', 'success')
        elif action == 'delete_user':
            user_whatsapp = request.form.get('whatsapp')
            UserGkach.query.filter_by(user_whatsapp=user_whatsapp).delete()
            db.session.commit()
            flash('Kont Gkach efase avèk siksè!', 'success')
        
        return redirect(url_for('admin.manage_gkach'))
    
    users_gkach = UserGkach.query.all()
    return render_template('admin_manage_gkach.html', users_gkach=users_gkach)


@admin_bp.route('/batches/create', methods=['POST'])
@login_required
@admin_required
def create_batch():
    """Create a new ad batch for viral sharing"""
    from app.models.batch import Batch
    from app.models.batch_ad import BatchAd

    try:
        # Get approved ads not currently in a batch
        available_ads = Ad.query.filter_by(admin_status='approved', batch_id=None).limit(5).all()
        
        if len(available_ads) < 5:
            flash('Pa gen ase piblisite apwouve (bezwen 5) pou kreye yon pakèt.', 'error')
            return redirect(url_for('admin.dashboard'))

        batch_id = str(uuid.uuid4())
        new_batch = Batch(batch_id=batch_id, created_at=datetime.utcnow())
        db.session.add(new_batch)

        for idx, ad in enumerate(available_ads):
            junction = BatchAd(batch_id=batch_id, ad_id=ad.ad_id, position=idx)
            db.session.add(junction)
            ad.batch_id = batch_id

        db.session.commit()
        flash('Nouvo pakèt piblisite kreye avèk siksè!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Erè nan kreyasyon pakèt: {str(e)}', 'error')

    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/api/popup_settings', methods=['GET'])
def get_popup_settings_api():
    settings = AdminSettings.get_all_settings()
    # Convert boolean strings back to actual booleans
    settings['enable_account_reminder'] = settings.get('enable_account_reminder') == 'True'
    settings['enable_gkach_notice'] = settings.get('enable_gkach_notice') == 'True'
    settings['popup_interval_minutes'] = int(settings.get('popup_interval_minutes', 10))
    settings['gkach_required_amount'] = int(settings.get('gkach_required_amount', 1000))
    settings['gkach_target_date'] = settings.get('gkach_target_date', '2026-06-20')
    
    return jsonify(settings)


@admin_bp.route('/popup_settings', methods=['POST'])
@login_required
@admin_required
def popup_settings():
    if request.method == 'POST':
        AdminSettings.set_setting('enable_account_reminder', request.form.get('enable_account_reminder') == 'on')
        AdminSettings.set_setting('enable_gkach_notice', request.form.get('enable_gkach_notice') == 'on')
        AdminSettings.set_setting('popup_interval_minutes', request.form.get('popup_interval_minutes', type=int))
        AdminSettings.set_setting('gkach_target_date', request.form.get('gkach_target_date'))
        AdminSettings.set_setting('gkach_required_amount', request.form.get('gkach_required_amount', type=int))
    flash('Paramèt popup yo mete ajou avèk siksè!', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/ads/update', methods=['POST'])
@login_required
@admin_required
def update_ad_status():
    """Update ad admin status and payment status"""
    ad_id = request.form.get('ad_id')
    admin_status = request.form.get('status')
    payment_status = request.form.get('payment_status')
    
    if not ad_id:
        flash('ID piblisite obligatwa.', 'error')
        return redirect(url_for('admin.dashboard'))
    
    ad = Ad.query.filter_by(ad_id=ad_id).first()
    if not ad:
        flash('Piblisite pa jwenn.', 'error')
        return redirect(url_for('admin.dashboard'))
    
    if admin_status:
        ad.admin_status = admin_status
    if payment_status:
        ad.payment_status = payment_status
    
    db.session.commit()
    
    # Invalidate cache
    from app.services.redis_service import RedisService
    from app import redis_client
    RedisService(redis_client).invalidate_approved_ads()
    RedisService(redis_client).cache_delete(f"ad:{ad_id}")
    
    flash('Estati piblisite mete ajou avèk siksè!', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/ads/delete/<ad_id>', methods=['POST'])
@login_required
@admin_required
def admin_delete_ad(ad_id):
    """Delete ad (admin only)"""
    try:
        AdService.delete_ad(ad_id=ad_id)
        flash('Piblisite efase avèk siksè!', 'success')
    except Exception as e:
        flash(f'Erè nan efase piblisite: {str(e)}', 'error')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/batches/delete/<batch_id>', methods=['POST'])
@login_required
@admin_required
def delete_batch(batch_id):
    """Delete a batch"""
    from app.models.batch import Batch
    from app.models.batch_ad import BatchAd
    
    batch = Batch.query.filter_by(batch_id=batch_id).first()
    if not batch:
        flash('Gwoup pa jwenn.', 'error')
        return redirect(url_for('admin.dashboard'))
    
    # First, update ads in this batch to remove batch_id
    BatchAd.query.filter_by(batch_id=batch_id).delete()
    for ad in Ad.query.filter_by(batch_id=batch_id).all():
        ad.batch_id = None
    
    # Delete the batch
    db.session.delete(batch)
    db.session.commit()
    
    flash('Gwoup efase avèk siksè!', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/batches/edit/<batch_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_batch(batch_id):
    """View and edit a batch"""
    from app.models.batch import Batch
    from app.models.batch_ad import BatchAd

    batch = Batch.query.filter_by(batch_id=batch_id).first_or_404()

    if request.method == 'POST':
        # TODO: Implement batch editing (e.g., change ads in batch, etc.)
        flash('Modifikasyon gwoup ap vini byento!', 'info')
        return redirect(url_for('admin.edit_batch', batch_id=batch_id))
    
    batch_ads = BatchAd.query.filter_by(batch_id=batch_id).order_by(BatchAd.position).all()
    ads = [AdService.get_ad(ba.ad_id) for ba in batch_ads]
    
    # Get available ads (approved, not in any batch)
    available_ads = Ad.query.filter_by(admin_status='approved', batch_id=None).all()
    
    return render_template('admin_edit_batch.html', batch=batch, batch_ads=ads, available_ads=available_ads)


@admin_bp.route('/batches/<batch_id>/ads/<ad_id>/add', methods=['POST'])
@login_required
@admin_required
def add_ad_to_batch(batch_id, ad_id):
    """Add an ad to a batch"""
    from app.models.batch import Batch
    from app.models.batch_ad import BatchAd

    batch = Batch.query.filter_by(batch_id=batch_id).first_or_404()
    ad = Ad.query.filter_by(ad_id=ad_id).first_or_404()

    # Check if ad is already in a batch
    if ad.batch_id is not None:
        flash('Piblisite sa a deja nan yon gwoup!', 'error')
        return redirect(url_for('admin.edit_batch', batch_id=batch_id))

    # Get next position
    max_position = BatchAd.query.filter_by(batch_id=batch_id).count()
    batch_ad = BatchAd(batch_id=batch_id, ad_id=ad_id, position=max_position)
    db.session.add(batch_ad)
    ad.batch_id = batch_id
    db.session.commit()

    flash('Piblisite ajoute nan gwoup avèk siksè!', 'success')
    return redirect(url_for('admin.edit_batch', batch_id=batch_id))


@admin_bp.route('/batches/<batch_id>/ads/<ad_id>/remove', methods=['POST'])
@login_required
@admin_required
def remove_ad_from_batch(batch_id, ad_id):
    """Remove an ad from a batch"""
    from app.models.batch import Batch
    from app.models.batch_ad import BatchAd

    batch = Batch.query.filter_by(batch_id=batch_id).first_or_404()
    ad = Ad.query.filter_by(ad_id=ad_id).first_or_404()

    # Delete the batch ad
    BatchAd.query.filter_by(batch_id=batch_id, ad_id=ad_id).delete()
    ad.batch_id = None
    db.session.commit()

    # Reorder remaining ads
    remaining = BatchAd.query.filter_by(batch_id=batch_id).order_by(BatchAd.position).all()
    for i, ba in enumerate(remaining):
        ba.position = i
    db.session.commit()

    flash('Piblisite retire nan gwoup avèk siksè!', 'success')
    return redirect(url_for('admin.edit_batch', batch_id=batch_id))


# ═══════════════════════════════════════════
# PWA ADMIN CONFIGURATION ROUTES
# ═══════════════════════════════════════════

@admin_bp.route('/mobile-config')
@login_required
@admin_required
def mobile_config():
    """PWA / Mobile App Configuration Page (Admin SEVIS)"""
    from app.models.app_installation import AppInstallation
    
    # Get PWA settings
    pwa_settings = {
        'pwa_enabled': AdminSettings.get_setting('pwa_enabled', 'True'),
        'pwa_popup_title': AdminSettings.get_setting('pwa_popup_title', 'Installer Glory2YahPub'),
        'pwa_popup_description': AdminSettings.get_setting('pwa_popup_description', 
            'Accédez rapidement aux boutiques, publications, annonces et services depuis votre téléphone.'),
        'pwa_popup_button_text': AdminSettings.get_setting('pwa_popup_button_text', 'Installer maintenant'),
        'pwa_popup_delay_seconds': AdminSettings.get_setting('pwa_popup_delay_seconds', '5'),
        'pwa_ios_guide_enabled': AdminSettings.get_setting('pwa_ios_guide_enabled', 'True')
    }
    
    # Get installation statistics
    stats = AppInstallation.get_stats()
    
    return render_template(
        'admin_mobile_config.html',
        pwa_settings=pwa_settings,
        stats=stats,
        current_user=current_user
    )


@admin_bp.route('/mobile-config/update', methods=['POST'])
@login_required
@admin_required
def mobile_config_update():
    """Update PWA configuration settings"""
    try:
        # PWA enabled toggle
        AdminSettings.set_setting('pwa_enabled', 
            'True' if request.form.get('pwa_enabled') == 'on' else 'False')
        
        # Popup text settings
        if request.form.get('pwa_popup_title'):
            AdminSettings.set_setting('pwa_popup_title', request.form.get('pwa_popup_title'))
        if request.form.get('pwa_popup_description'):
            AdminSettings.set_setting('pwa_popup_description', request.form.get('pwa_popup_description'))
        if request.form.get('pwa_popup_button_text'):
            AdminSettings.set_setting('pwa_popup_button_text', request.form.get('pwa_popup_button_text'))
        
        # Popup delay
        delay = request.form.get('pwa_popup_delay_seconds', type=int)
        if delay and delay > 0:
            AdminSettings.set_setting('pwa_popup_delay_seconds', str(delay))
        
        # iOS guide toggle
        AdminSettings.set_setting('pwa_ios_guide_enabled',
            'True' if request.form.get('pwa_ios_guide_enabled') == 'on' else 'False')
        
        flash('Configuration aplikasyon mobil mete ajou avèk siksè!', 'success')
    except Exception as e:
        flash(f'Erè nan konfigirasyon: {str(e)}', 'error')
    
    return redirect(url_for('admin.mobile_config'))


