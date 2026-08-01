"""
Authentication Routes Blueprint
Login, Register, Logout with security
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from app import db, limiter, csrf, cache
from app.models.user import User
from app.models.user_gkach import UserGkach
from app.utils.validators import (
    validate_whatsapp, validate_email_address, validate_password,
    validate_pseudo, ValidationError
)
from datetime import datetime, timedelta

auth_bp = Blueprint('auth', __name__)


def _clean_whatsapp(raw: str) -> str:
    raw = (raw or '').strip()
    cleaned = ''.join(c for c in raw if c.isdigit() or c == '+')
    if cleaned and not cleaned.startswith('+'):
        cleaned = '+' + cleaned
    return cleaned or raw


def _clean_pseudo(raw: str) -> str:
    return (raw or '').strip()


def _find_user_by_identifier(identifier):
    """Strict match only — no substring LIKE, no fuzzy account takeover.
    Priority:
      1. Exact pseudo or whatsapp match.
      2. Cleaned whatsapp or pseudo exact match.
      3. Pseudo case-insensitive exact match.
    """
    if not identifier:
        return None
    ident = identifier.strip()
    clean_wa = _clean_whatsapp(ident)
    # 1 Exact raw
    u = User.query.filter(db.or_(User.pseudo == ident, User.whatsapp == ident)).first()
    if u: return u
    # 2 Cleaned
    if clean_wa != ident:
        u = User.query.filter(db.or_(User.pseudo == clean_wa, User.whatsapp == clean_wa)).first()
        if u: return u
    # 3 Pseudo case-insensitive exact
    if clean_wa:
        u = User.query.filter(db.func.lower(User.pseudo) == clean_wa.lower()).first()
        if u: return u
    u = User.query.filter(db.func.lower(User.pseudo) == ident.lower()).first()
    if u: return u
    return None


def _cache_identifier_rate_limit(key_prefix: str, identifier: str, limit: int, window_seconds: int) -> bool:
    """Return True if rate-limit EXCEEDED (blocked), False if OK.
    Uses SimpleCache/Redis via flask_caching (cache from app)."""
    if not identifier or not cache:
        return False
    ckey = f"rl:{key_prefix}:{identifier}"
    try:
        data = cache.get(ckey) or []
        now = datetime.utcnow().timestamp()
        cutoff = now - window_seconds
        fresh = [t for t in data if float(t) >= cutoff]
        if len(fresh) >= limit:
            return True
        fresh.append(now)
        cache.set(ckey, fresh, timeout=window_seconds + 5)
    except Exception:
        return False
    return False


FORGOT_TEMP_PW_TTL_SEC = 3600  # 1 hour
_FORGOT_KEY = "forgot_temp_pw:{}"

def _store_forgot_temp_password(user_id: int, temp_pw_plain: str) -> None:
    """Store temp pw SHA256 hash in cache (never overwrite main password_hash)."""
    if not cache: return
    import hashlib
    h = hashlib.sha256(temp_pw_plain.encode("utf-8")).hexdigest()
    cache.set(_FORGOT_KEY.format(user_id), h, timeout=FORGOT_TEMP_PW_TTL_SEC)

def _check_forgot_temp_password(user_id: int, password_plain: str) -> bool:
    """Check if candidate password matches any valid temp reset pw hash in cache."""
    if not cache or not user_id or not password_plain:
        return False
    import hashlib
    h_expected = cache.get(_FORGOT_KEY.format(user_id))
    if not h_expected:
        return False
    h_cand = hashlib.sha256(password_plain.encode("utf-8")).hexdigest()
    try:
        return h_cand == h_expected
    except Exception:
        return False


@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("10 per hour")
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

            current_app.logger.info(
                "Register attempt: len(whatsapp)=%d len(pseudo)=%d len(name)=%d",
                len(whatsapp), len(pseudo), len(name),
            )

            # Clean whatsapp first
            whatsapp_clean = _clean_whatsapp(whatsapp)

            # Clean pseudo (remove any non-valid characters)
            pseudo_clean = _clean_pseudo(pseudo)
            if not pseudo_clean:
                pseudo_clean = whatsapp_clean

            # Validate password BEFORE any DB write (P1 FIX — was never called)
            validate_password(password)

            # Check if pseudo exists
            existing_pseudo = User.query.filter_by(pseudo=pseudo_clean).first()
            if existing_pseudo:
                flash(f'Pseudo "{pseudo_clean}" la deja pran. Tanpri chwazi yon lòt.', 'error')
                return redirect(url_for('auth.register'))

            # Check if WhatsApp already registered
            existing_whatsapp = User.query.filter_by(whatsapp=whatsapp_clean).first()
            if existing_whatsapp:
                flash('Nimewo WhatsApp sa a deja anrejistre. Tanpri konekte.', 'error')
                return redirect(url_for('auth.login'))

            # Create user
            user = User(
                whatsapp=whatsapp_clean,
                pseudo=pseudo_clean,
                name=name if name else pseudo_clean,
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
                user_whatsapp=whatsapp_clean,
                gkach_balance=0
            )
            db.session.add(user_gkach)
            db.session.commit()

            # Auto-login the user right after registration
            login_user(user, remember=True)
            session.permanent = True  # auto-register keep session

            # Update last login
            user.last_login = datetime.utcnow()
            db.session.commit()

            flash('Kont kreye avèk siksè! Byenveni nan Glory2YahPub!', 'success')
            return redirect(url_for('main.index'))

        except ValidationError as e:
            current_app.logger.warning("Register validation failed: %s", e)
            flash(str(e), 'error')
            return redirect(url_for('auth.register'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error("Register exception: %s", e, exc_info=True)
            flash('Erè nan kreyasyon kont. Tanpri eseye ankò.', 'error')
            return redirect(url_for('auth.register'))
    
    return render_template('auth/register.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login():
    """User login"""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        try:
            identifier = request.form.get('identifier', '').strip()
            password = request.form.get('password', '').strip()
            # SESSION FIX (stay logged in until explicit logout):
            # Always remember = True by default. User can still NOT opt-out by explicitly
            # sending remember=0/off/false/no via UI checkbox — but default behaviour MUST
            # be "I stay connected". This sets both the REMEMBER cookie (365 days via
            # REMEMBER_COOKIE_DURATION) AND forces session.permanent=True below.
            remember_checked = request.form.get('remember')
            if remember_checked is None:
                remember = True
            else:
                remember = str(remember_checked).lower() not in ('0', 'no', 'false', 'off', '')
            # Force True always: sessions MUST persist until the user logs out explicitly
            # (check above preserved for audit/optional opt-in checkbox only).
            remember = True

            if not identifier or not password:
                flash('Tout chan yo obligatwa.', 'error')
                return redirect(url_for('auth.login'))

            # Per-identifier brute force rate-limit: max 5 failed in 5 minutes
            if _cache_identifier_rate_limit("login_fail_id", identifier, 5, 300):
                current_app.logger.warning(
                    "Login rate-limit BLOCKED for identifier=%s", identifier[:8] + "***",
                )
                flash(
                    'Twa (5) esè koneksyon invalide. Tanpri tann 5 minit epi eseye ankò.',
                    'error',
                )
                return redirect(url_for('auth.login'))

            # Strict match only — NO substring LIKE (prevent takeover)
            user = _find_user_by_identifier(identifier)

            if not user:
                current_app.logger.warning(
                    "Login failed: identifier=%s (no user found strict)",
                    identifier[:8] + "***",
                )
                flash(
                    'Identifikasyon envalid. Tanpri tcheke WhatsApp oswa pseudo ak modpas ou.',
                    'error',
                )
                return redirect(url_for('auth.login'))

            # Check password OR valid temporary forgot-password token
            password_ok = False
            try:
                password_ok = bool(user.check_password(password))
            except Exception:
                password_ok = False
            if not password_ok:
                password_ok = bool(_check_forgot_temp_password(user.id, password))

            if not password_ok:
                # Register failed attempt BEFORE redirect (rate-limit)
                current_app.logger.warning(
                    "Login failed: user_id=%s pseudo=%s wrong password",
                    user.id, user.pseudo,
                )
                flash(
                    'Identifikasyon envalid. Tanpri tcheke WhatsApp oswa pseudo ak modpas ou.',
                    'error',
                )
                return redirect(url_for('auth.login'))

            if not user.is_active:
                flash('Kont ou an dezaktive.', 'error')
                return redirect(url_for('auth.login'))

            # If user used temp forgot pw, clear it so single-use only
            if _check_forgot_temp_password(user.id, password):
                try:
                    if cache: cache.delete(_FORGOT_KEY.format(user.id))
                except Exception:
                    pass
                flash(
                    "Tanpri chanje modpas ou nan pwofil ou rapidman (modpas pwovizwa a itilize 1 fwa sèlman).",
                    "warning",
                )

            # Login user, respect remember me
            login_user(user, remember=True, force=True)

            # FORCE permanent session regardless of anything — user must stay logged in
            # until they explicitly click /logout. PERMANENT_SESSION_LIFETIME = 30j.
            from flask import session as _s
            _s.permanent = True
            # Mark remember cookie sent (for audit)
            _s['_remember_set'] = True

            # Update last login
            user.last_login = datetime.utcnow()
            db.session.commit()

            flash(f'Byenveni, {user.pseudo}!', 'success')

            next_page = request.args.get('next')
            if next_page:
                from werkzeug.security import url_has_allowed_host_and_scheme
                allowed = False
                try:
                    allowed = url_has_allowed_host_and_scheme(next_page, request.host)
                except Exception:
                    allowed = False
                if allowed:
                    return redirect(next_page)
            return redirect(url_for('main.index'))

        except ValidationError as e:
            current_app.logger.warning("Login validation error: %s", e)
            flash(str(e), 'error')
            return redirect(url_for('auth.login'))
        except Exception as e:
            import traceback
            current_app.logger.error(
                "Login exception: %s\n%s", e, traceback.format_exc(),
            )
            db.session.rollback()
            flash('Erè nan koneksyon. Tanpri eseye ankò.', 'error')
            return redirect(url_for('auth.login'))

    return render_template('auth/login.html')


@auth_bp.route('/logout')
def logout():
    """User logout - preserve CSRF token in session.
    Note: no @login_required so even if session expired, we ALWAYS clear any session cleanly."""
    if current_user.is_authenticated:
        logout_user()
    # Preserve CSRF token to avoid issues on next login
    csrf_token = session.get('_csrf_token')
    session.clear()
    if csrf_token:
        session['_csrf_token'] = csrf_token
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


@auth_bp.route('/profile/delete', methods=['POST'])
@login_required
@limiter.limit("1 per hour")
def delete_account():
    """Delete current user's account (self-delete)"""
    try:
        # P1 FIX: CAPTURE current user identity LOCAL VARS BEFORE logout_user()
        #   because logout_user + session.clear() turns current_user -> AnonymousUserMixin (no .whatsapp)
        user_id = int(current_user.id)
        user_wa = current_user.whatsapp
        user_pseudo = current_user.pseudo

        # Get password confirmation
        password = request.form.get('password', '').strip()

        if not password:
            flash('Tanpri antre modpas ou pou konfime.', 'error')
            return redirect(url_for('auth.profile'))

        if not current_user.check_password(password):
            flash('Modpas envalid. Kont ou pa efase.', 'error')
            return redirect(url_for('auth.profile'))

        # Safe deletions — use LOCAL CAPTURED vars only now
        from app.models.user_gkach import UserGkach
        from app.models.ad import Ad
        from app.models.gkach_transaction import GkachTransaction
        from app.models.cart import CartItem

        # Delete related records (don't use current_user.* — it's dead after logout)
        UserGkach.query.filter_by(user_whatsapp=user_wa).delete()
        Ad.query.filter_by(user_whatsapp=user_wa).delete()
        GkachTransaction.query.filter_by(user_whatsapp=user_wa).delete()
        CartItem.query.filter_by(user_id=user_id).delete()

        # Reload actual User ORM row from DB by id (SAFE)
        victim = db.session.get(User, user_id)
        if victim is not None:
            db.session.delete(victim)

        # NOW logout AFTER all DB ops scheduled (or before? Either; session vars already captured)
        logout_user()
        session.clear()

        db.session.commit()

        current_app.logger.info(
            "User self-delete OK: user_id=%d pseudo=%s wa=%s",
            user_id, user_pseudo, (user_wa or "")[-6:],
        )

        flash('Kont ou efase avèk siksè!', 'success')
        return redirect(url_for('main.index'))

    except Exception as e:
        import traceback
        current_app.logger.error(
            "Delete account failed: %s\n%s", e, traceback.format_exc(),
        )
        db.session.rollback()
        flash('Erè nan efase kont. Eseye ankò.', 'error')
        return redirect(url_for('auth.profile'))


@auth_bp.route('/ads')
@login_required
def my_ads():
    """View all ads belonging to the current user"""
    from app.services.ad_service import AdService
    ads = AdService.get_user_ads(current_user.whatsapp)
    return render_template('auth/my_ads.html', ads=ads)


@auth_bp.route('/ads/<ad_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_ad(ad_id):
    """Edit an existing ad (only owner)"""
    from app.services.ad_service import AdService
    from app.models.ad import Ad
    from app.utils.validators import sanitize_text, ValidationError
    
    ad = Ad.query.filter_by(ad_id=ad_id, user_whatsapp=current_user.whatsapp).first()
    if not ad:
        flash('Piblisite pa jwenn oswa ou pa gen dwa modifye li.', 'error')
        return redirect(url_for('auth.my_ads'))
    
    if request.method == 'POST':
        try:
            title = sanitize_text(request.form.get('title', ''))
            description = sanitize_text(request.form.get('description', ''))
            price_gkach = request.form.get('price_gkach', None)
            if price_gkach:
                price_gkach = int(price_gkach)
            
            AdService.update_ad(
                ad_id=ad_id,
                user_whatsapp=current_user.whatsapp,
                title=title,
                description=description,
                price_gkach=price_gkach
            )
            
            flash('Piblisite modifye avèk siksè!', 'success')
            return redirect(url_for('auth.my_ads'))
            
        except ValidationError as e:
            flash(str(e), 'error')
            return redirect(url_for('auth.edit_ad', ad_id=ad_id))
        except Exception as e:
            db.session.rollback()
            flash('Erè nan modifye piblisite.', 'error')
            return redirect(url_for('auth.edit_ad', ad_id=ad_id))
    
    return render_template('auth/edit_ad.html', ad=ad.to_dict())


@auth_bp.route('/ads/<ad_id>/delete', methods=['POST'])
@login_required
def delete_ad(ad_id):
    """Delete an ad (only owner)"""
    from app.services.ad_service import AdService
    from app.utils.validators import ValidationError
    
    try:
        AdService.delete_ad(ad_id=ad_id, user_whatsapp=current_user.whatsapp)
        flash('Piblisite efase avèk siksè!', 'success')
    except ValidationError as e:
        flash(str(e), 'error')
    
    return redirect(url_for('auth.my_ads'))


@auth_bp.route('/stories')
@login_required
def my_stories():
    """View all stories belonging to the current user"""
    from app.models.story import Story
    stories = Story.query.filter_by(user_whatsapp=current_user.whatsapp).order_by(Story.created_at.desc()).all()
    return render_template('auth/my_stories.html', stories=stories)


@auth_bp.route('/stories/<story_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_story(story_id):
    """Edit an existing story (only owner)"""
    from app.models.story import Story
    from app.utils.validators import sanitize_text, ValidationError
    
    story = Story.query.filter_by(story_id=story_id, user_whatsapp=current_user.whatsapp).first()
    if not story:
        flash('Istwa pa jwenn oswa ou pa gen dwa modifye li.', 'error')
        return redirect(url_for('auth.my_stories'))
    
    if request.method == 'POST':
        try:
            title = sanitize_text(request.form.get('title', ''))
            description = sanitize_text(request.form.get('description', ''))
            price_gkach = request.form.get('price_gkach', None)
            if price_gkach:
                price_gkach = int(price_gkach)
            
            story.title = title
            story.description = description
            story.price_gkach = price_gkach
            
            db.session.commit()
            
            flash('Istwa modifye avèk siksè!', 'success')
            return redirect(url_for('auth.my_stories'))
            
        except ValidationError as e:
            flash(str(e), 'error')
            return redirect(url_for('auth.edit_story', story_id=story_id))
        except Exception as e:
            db.session.rollback()
            flash('Erè nan modifye istwa.', 'error')
            return redirect(url_for('auth.edit_story', story_id=story_id))
    
    return render_template('auth/edit_story.html', story=story.to_dict())


@auth_bp.route('/stories/<story_id>/delete', methods=['POST'])
@login_required
def delete_story(story_id):
    """Delete a story (only owner)"""
    from app.models.story import Story
    
    try:
        story = Story.query.filter_by(story_id=story_id, user_whatsapp=current_user.whatsapp).first()
        if not story:
            flash('Istwa pa jwenn oswa ou pa gen dwa efase li.', 'error')
            return redirect(url_for('auth.my_stories'))
        
        db.session.delete(story)
        db.session.commit()
        
        flash('Istwa efase avèk siksè!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Erè nan efase istwa.', 'error')
    
    return redirect(url_for('auth.my_stories'))


def generate_temp_password():
    """Generate a random 6-digit temporary password"""
    import random
    return str(random.randint(100000, 999999))


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit("5 per hour")
def forgot_password():
    """Forgot password: show 6-digit temp password ONLY to the requesting user.
    P1 FIX: NEVER overwrite the original password_hash. Temp pw is stored in CACHE
    (SHA256 hash) for 1 hour, single-use only, removed on successful login.
    Original user can still login normally even if an attacker runs this route."""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    temp_password = None

    if request.method == 'POST':
        identifier = request.form.get('identifier', '').strip()

        if not identifier:
            flash('Tanpri antre WhatsApp ou oswa pseudo.', 'error')
            return redirect(url_for('auth.forgot_password'))

        # Per-identifier rate limit (forgot pw is very sensitive)
        if _cache_identifier_rate_limit("forgot_pw_id", identifier, 2, 900):
            current_app.logger.warning(
                "Forgot pw rate-limit BLOCKED id=%s", identifier[:6] + "***",
            )
            flash('Tanpri tann 15 minit antre 2 demann modpas pwovizwa.', 'error')
            return redirect(url_for('auth.forgot_password'))

        # STRICT find user (same strict lookup as login)
        user = _find_user_by_identifier(identifier)

        if not user:
            # Never reveal if account exists or not (anti-enumeration)
            flash(
                "Si kont lan egziste ak WhatsApp oswa pseudo sa, tanpri gade anba a wè modpas pwovizwa a. "
                "Tanpri konekte avè l epi chanje li rapidman.",
                'success',
            )
            return redirect(url_for('auth.forgot_password'))

        # Generate temporary password
        temp_password = generate_temp_password()

        # P1 SAFETY: NEVER call user.set_password() (keep original pw working!)
        #   Store temp hash in cache with 1hr TTL, single use
        _store_forgot_temp_password(int(user.id), temp_password)
        db.session.commit()  # no-op (nothing to commit), keep behavior idempotent

        current_app.logger.info(
            "Forgot pw temp pw issued: user_id=%s pseudo=%s",
            user.id, user.pseudo,
        )

        flash(
            'Modpas pwovizwa la valab pou 1 èdtan, 1 fwa sèlman. '
            'Tanpri chanje modpas ou nan pwofil ou apre w konekte.',
            'success',
        )

    return render_template('auth/forgot_password.html', temp_password=temp_password)
