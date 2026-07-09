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


