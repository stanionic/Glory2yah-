"""
Authentication Routes Blueprint
Login, Register, Logout with security
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from app import db, limiter, csrf
from app.models.user import User
from app.models.user_gkach import UserGkach
from app.utils.validators import (
    validate_whatsapp, validate_email_address, validate_password,
    validate_pseudo, ValidationError
)
from app.utils.security import generate_csrf_token
from datetime import datetime

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("5 per hour")
def register():
    """User registration"""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        try:
            # Get form data
            whatsapp = request.form.get('whatsapp', '').strip()
            pseudo = request.form.get('pseudo', '').strip()
            name = request.form.get('name', '').strip()
            password = request.form.get('password', '').strip()
            bio = request.form.get('bio', '').strip()
            
            # Validate
            whatsapp = validate_whatsapp(whatsapp)
            pseudo = validate_pseudo(pseudo)
            validate_password(password)
            
            # Check if pseudo exists
            if User.query.filter_by(pseudo=pseudo).first():
                flash('Pseudo sa a deja pran.', 'error')
                return redirect(url_for('auth.register'))
            
            # Check if WhatsApp already registered
            existing = User.query.filter(
                User.whatsapp == whatsapp,
                User.password_hash.isnot(None)
            ).first()
            
            if existing:
                flash('Numéro WhatsApp sa a deja anrejistre.', 'error')
                return redirect(url_for('auth.login'))
            
            # Create user
            user = User(
                whatsapp=whatsapp,
                pseudo=pseudo,
                name=name,
                bio=bio,
                auth_provider='whatsapp',
                is_active=True
            )
            user.set_password(password)
            
            db.session.add(user)
            db.session.commit()
            
            # Create Gkach account
            user_gkach = UserGkach(
                user_id=user.id,
                user_whatsapp=whatsapp,
                gkach_balance=0
            )
            db.session.add(user_gkach)
            db.session.commit()
            
            flash('Kont kreye avèk siksè! Konekte kounye a.', 'success')
            return redirect(url_for('auth.login'))
            
        except ValidationError as e:
            flash(str(e), 'error')
            return redirect(url_for('auth.register'))
        except Exception as e:
            db.session.rollback()
            flash('Erè nan kreyasyon kont. Eseye ankò.', 'error')
            return redirect(url_for('auth.register'))
    
    return render_template('auth/register.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per hour")
@csrf.exempt
def login():
    """User login"""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        try:
            identifier = request.form.get('identifier', '').strip()
            password = request.form.get('password', '').strip()
            remember = request.form.get('remember', False)
            
            if not identifier or not password:
                flash('Tout chan yo obligatwa.', 'error')
                return redirect(url_for('auth.login'))
            
            # Find user by pseudo or whatsapp
            user = User.query.filter(
                db.or_(
                    User.pseudo == identifier,
                    User.whatsapp == identifier
                )
            ).first()
            
            if not user or not user.check_password(password):
                flash('Identifikasyon envalid.', 'error')
                return redirect(url_for('auth.login'))
            
            if not user.is_active:
                flash('Kont ou an dezaktive.', 'error')
                return redirect(url_for('auth.login'))
            
            # Login user
            login_user(user, remember=remember)
            
            # Update last login
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            # Note: Flask's built-in session object doesn't support regenerate().
            # Removing this to avoid login failures/redirect loops.
            
            flash(f'Byenveni, {user.pseudo}!', 'success')
            
            # Redirect to next page or home
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('main.index'))
            
        except Exception as e:
            flash('Erè nan koneksyon. Eseye ankò.', 'error')
            return redirect(url_for('auth.login'))
    
    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    """User logout"""
    logout_user()
    session.clear()
    flash('Ou dekonekte avèk siksè.', 'info')
    return redirect(url_for('main.index'))


@auth_bp.route('/profile')
@login_required
def profile():
    """User profile"""
    gkach_balance = current_user.get_gkach_balance()
    
    return render_template(
        'auth/profile.html',
        user=current_user,
        gkach_balance=gkach_balance
    )


@auth_bp.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    """Edit user profile"""
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            bio = request.form.get('bio', '').strip()
            
            current_user.name = name
            current_user.bio = bio
            
            # Handle profile photo upload
            if 'profile_photo' in request.files:
                file = request.files['profile_photo']
                if file and file.filename:
                    from app.utils.validators import validate_file_upload
                    from app.utils.security import secure_filename_extended
                    from flask import current_app
                    import os
                    
                    try:
                        validate_file_upload(
                            file,
                            current_app.config['ALLOWED_IMAGE_EXTENSIONS']
                        )
                        
                        filename = secure_filename_extended(file.filename)
                        filepath = os.path.join(
                            current_app.config['UPLOAD_FOLDER'],
                            filename
                        )
                        file.save(filepath)
                        
                        current_user.profile_photo = filename
                    except ValidationError as e:
                        flash(str(e), 'error')
                        return redirect(url_for('auth.edit_profile'))
            
            db.session.commit()
            flash('Pwofil mete ajou avèk siksè!', 'success')
            return redirect(url_for('auth.profile'))
            
        except Exception as e:
            db.session.rollback()
            flash('Erè nan mizajou pwofil. Eseye ankò.', 'error')
            return redirect(url_for('auth.edit_profile'))
    
    return render_template('auth/edit_profile.html', user=current_user)


@auth_bp.route('/profile/change-password', methods=['POST'])
@login_required
@limiter.limit("3 per hour")
def change_password():
    """Change user password"""
    try:
        current_password = request.form.get('current_password', '').strip()
        new_password = request.form.get('new_password', '').strip()
        
        if not current_user.check_password(current_password):
            return jsonify({'success': False, 'message': 'Modpas aktyèl envalid'}), 400
        
        validate_password(new_password)
        
        current_user.set_password(new_password)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Modpas chanje avèk siksè!'})
        
    except ValidationError as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': 'Erè nan chanjman modpas'}), 500
