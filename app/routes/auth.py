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


def _wants_json():
    """True for the fetch() calls made by the OTP widget.

    Keyed on an explicit header rather than the Accept mime types: browsers send
    Accept: text/html,*/* on fetch too, so mime negotiation would mis-route the
    AJAX call and hand back a whole HTML page.
    """
    return (request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            or request.form.get('ajax') == '1')


def _is_pending_signup(user):
    """An account created by the OTP signup flow that never finished verifying.

    The `has_history` test is what makes this precise. `is_active=False` alone
    also matches legacy accounts an administrator switched off, and those people
    must keep seeing "contact administrator" - not be funnelled into a phone
    verification they were never enrolled in.
    """
    if user is None or user.is_active or user.phone_verified:
        return False
    try:
        from app.services import otp_service
        return otp_service.has_history(user.whatsapp, user_id=user.id)
    except Exception:
        return False


def _pending_verify_user():
    """The still-unverified account this browser is mid-signup with, or None."""
    uid = session.get('pending_verify_uid')
    if not uid:
        return None
    try:
        user = db.session.get(User, int(uid))
    except (TypeError, ValueError):
        session.pop('pending_verify_uid', None)
        return None
    if user is None or user.phone_verified or user.is_active:
        # Already finished (back-button, or verified in another tab): do not
        # offer a second activation of a live account.
        session.pop('pending_verify_uid', None)
        return None
    if not _is_pending_signup(user):
        session.pop('pending_verify_uid', None)
        return None
    return user


def _mask_phone(raw):
    """+50942882076 -> +509•••••2076 (show enough to recognise the number)."""
    s = str(raw or '')
    if len(s) <= 6:
        return s[:2] + '•' * max(0, len(s) - 2)
    return s[:4] + '•' * (len(s) - 7) + s[-3:]


def _activate_after_verification(user):
    """Flip a pending signup into a live, logged-in, bonus-credited account.

    Order matters: the account is committed as active BEFORE the welcome bonus is
    attempted, so a bonus failure can never strand a verified user outside the
    app, and can never be re-claimed (issue_welcome_bonus is idempotent).
    """
    user.is_active = True
    user.phone_verified = True
    user.last_login = datetime.utcnow()
    db.session.commit()

    try:
        from app.services.gkach_service import GkachService
        GkachService.issue_welcome_bonus(user.whatsapp, _commit=True)
    except Exception as exc:
        current_app.logger.error(
            'Welcome bonus failed for verified user %s: %s', user.id, exc, exc_info=True)

    login_user(user, remember=True)
    session.permanent = True
    session.pop('pending_verify_uid', None)


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
    # 3 Pseudo case-insensitive exact (compare ident only — the old code compared
    #   pseudo against clean_wa, which is the *cleaned whatsapp* not the pseudo;
    #   that redundant step could never match a real user and is removed).
    u = User.query.filter(db.func.lower(User.pseudo) == ident.lower()).first()
    if u: return u
    return None


def _find_users_by_identifier(identifier):
    """EVERY strict-matching account for one typed identifier, best candidate first.

    Why a list and not `.first()`: `users.whatsapp` is indexed but NOT unique, so
    one person can own several rows — legacy accounts created before phone
    normalisation ('+509' vs '+50942882076'), or a re-registration made when the
    first one seemed unreachable. `User.query.filter(...).first()` then returned
    an ARBITRARY row (SQLite: the oldest), and the typed password — which belongs
    to the account they actually use — was verified against the wrong row and
    rejected: "Modpas ou pa koresponn ak kont sa a". The user's only way back in
    then looks like creating yet another account, which is precisely the reported
    bug. The password is what identifies the account, so login tries all
    candidates and keeps the one that matches.

    Ordering: pseudo exact (a pseudo is unique, so it is unambiguous), then the
    WhatsApp matches most-recently-active first, then cleaned variants, then the
    case-insensitive pseudo. Never fuzzy: only exact equality, so no takeover.
    """
    if not identifier:
        return []
    ident = identifier.strip()
    clean_wa = _clean_whatsapp(ident)
    recent = db.func.coalesce(User.last_login, User.created_at)

    seen, out = set(), []

    def _add(rows):
        for u in rows:
            if u is not None and u.id not in seen:
                seen.add(u.id)
                out.append(u)

    _add(User.query.filter(User.pseudo == ident).all())
    _add(User.query.filter(User.whatsapp == ident).order_by(recent.desc(), User.id.desc()).all())
    if clean_wa and clean_wa != ident:
        _add(User.query.filter(User.pseudo == clean_wa).all())
        _add(User.query.filter(User.whatsapp == clean_wa).order_by(recent.desc(), User.id.desc()).all())
    _add(User.query.filter(db.func.lower(User.pseudo) == ident.lower()).all())
    return out


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

            # Validate & clean whatsapp FIRST (P1 FIX — validate_whatsapp was never called,
            # which allowed corrupted accounts like "+509" or "+509ABC" to be created,
            # and those accounts could never log in properly).
            whatsapp_clean = validate_whatsapp(whatsapp)

            # Clean pseudo (remove any non-valid characters)
            pseudo_clean = _clean_pseudo(pseudo)
            if not pseudo_clean:
                # Fallback: derive pseudo from phone; strip '+' because phone format
                # (+509...) is not a valid pseudo (letters/digits/_/- only).
                pseudo_clean = whatsapp_clean.replace('+', '')

            # Validate pseudo (P1 FIX — was never called)
            validate_pseudo(pseudo_clean)

            # Validate password BEFORE any DB write (P1 FIX — was never called)
            validate_password(password)

            # --- duplicate handling -------------------------------------------
            # A never-verified account for this pseudo/number is the SAME human
            # retrying a signup that stalled, not a squatter: blocking them on a
            # uniqueness error they cannot resolve themselves is how you lose a
            # user for good. So a pending signup resumes; a real account still
            # errors as before.
            existing_pseudo = User.query.filter_by(pseudo=pseudo_clean).first()
            existing_whatsapp = User.query.filter_by(whatsapp=whatsapp_clean).first()

            pending_retry = existing_pseudo if _is_pending_signup(existing_pseudo) else None
            if pending_retry is None and _is_pending_signup(existing_whatsapp):
                pending_retry = existing_whatsapp

            if pending_retry is not None and existing_pseudo is not None \
                    and existing_whatsapp is not None \
                    and existing_pseudo.id != existing_whatsapp.id:
                # pseudo belongs to one pending account, number to another:
                # ambiguous, do not silently merge two rows.
                flash('Gen konfli ak yon kont an atant verifikasyon. Tanpri konekte oswa kontakte nou.', 'error')
                return redirect(url_for('auth.register'))

            if pending_retry is None:
                if existing_pseudo:
                    flash(f'Pseudo "{pseudo_clean}" la deja pran. Tanpri chwazi yon lòt.', 'error')
                    return redirect(url_for('auth.register'))

                if existing_whatsapp:
                    flash('Nimewo WhatsApp sa a deja anrejistre. Tanpri konekte.', 'error')
                    return redirect(url_for('auth.login'))

            if pending_retry is not None:
                # Resume the stalled signup on the existing row (keeps the same
                # id, so no orphan Gkach account is created either).
                user = pending_retry
                user.whatsapp = whatsapp_clean
                user.pseudo = pseudo_clean
                user.name = name if name else pseudo_clean
                user.set_password(password)
                db.session.commit()
            else:
                # Create user - PENDING: is_active stays False until the WhatsApp
                # code is confirmed, which also keeps Flask-Login's default
                # `is_active` check from ever handing out a session.
                user = User(
                    whatsapp=whatsapp_clean,
                    pseudo=pseudo_clean,
                    name=name if name else pseudo_clean,
                    bio=bio,
                    auth_provider='whatsapp',
                    is_active=False,
                    phone_verified=False
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

            # No auto-login and NO welcome bonus here: the 500-Gkach signup gift
            # is issued only after the number is proven (see verify_phone),
            # otherwise anyone could mint bonuses with numbers they do not own.
            from app.services import otp_service
            _otp, delivered_via = otp_service.issue_and_send(
                whatsapp_clean, user_id=user.id, ip_address=request.remote_addr
            )
            session['pending_verify_uid'] = user.id

            if delivered_via:
                if delivered_via == 'dev_fallback':
                    flash(
                        f'Mod DEV: Kòd OTP la: {_otp.dev_code}',
                        'info',
                    )
                else:
                    flash('Nou voye yon kòd 6 chif sou WhatsApp ou. Tanpri antre l pou aktive kont ou.', 'info')
            else:
                # Honest failure: the account is waiting, but no gateway could
                # reach them. Tell the user instead of showing a spinner forever.
                flash(
                    'Kont ou an kreye men nou pa rive voye kòd la WhatsApp kounye a. '
                    'Eseye "Voye kòd la ankò" oswa kontakte administrateur a.',
                    'error'
                )
            return redirect(url_for('auth.verify_phone'))

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


@auth_bp.route('/verify', methods=['GET', 'POST'])
@limiter.limit("60 per hour")
def verify_phone():
    """Enter the 6-digit WhatsApp code to activate a freshly created account.

    The account already exists (created by :func:`register`) but is inactive, so
    nothing here needs to survive a refresh or a back-button: the pending row is
    the state, the session only points at it.
    """
    user = _pending_verify_user()
    if user is None:
        if current_user.is_authenticated:
            return redirect(url_for('main.index'))
        flash('Pa gen yon enskripsyon an atant pou verifye. Kreye yon kont anvan.', 'info')
        return redirect(url_for('auth.register'))

    from app.services import otp_service

    if request.method == 'POST':
        status, _row = otp_service.verify(user.whatsapp, request.form.get('code', ''))
        st = otp_service.state(user.whatsapp)

        if status == otp_service.OK:
            _activate_after_verification(user)
            message = 'Kont ou aktif! Byenveni nan Glory2YahPub 🎉'
            if _wants_json():
                return jsonify({'ok': True, 'message': message,
                                'redirect': url_for('main.index')})
            flash(message, 'success')
            return redirect(url_for('main.index'))

        messages = {
            otp_service.WRONG: 'Kòd la pa kòrèk. Eseye ankò.',
            otp_service.EXPIRED: 'Kòd la ekspire. Tanpri mande yon lòt.',
            otp_service.LOCKED: 'Twòp tantativ. Tanpri mande yon nouvo kòd.',
            otp_service.MISSING: 'Tanpri antre kòd 6 chif la.',
        }
        message = messages.get(status, 'Kòd la pa valide.')

        if _wants_json():
            # Always HTTP 200: the request itself succeeded, `ok` carries the
            # verdict. A 4xx here would push the widget into its error branch
            # and lose the specific message (and the attempts budget).
            return jsonify({
                'ok': False,
                'status': status,
                'message': message,
                'resend_in': st.get('resend_in', 0),
                'attempts_left': st.get('attempts_left', 0),
            })

        flash(message, 'error')
        if status in (otp_service.EXPIRED, otp_service.LOCKED):
            # No auto-reissue: sending WhatsApp messages has a cost and an
            # abusive caller could otherwise force one per failed attempt.
            session['otp_suggest_resend'] = True
        return redirect(url_for('auth.verify_phone'))

    st = otp_service.state(user.whatsapp)
    suggest_resend = bool(session.pop('otp_suggest_resend', False)) or not st.get('usable', False)
    return render_template(
        'auth/verify_phone.html',
        masked_phone=_mask_phone(user.whatsapp),
        pseudo=user.pseudo,
        otp_state=st,
        suggest_resend=suggest_resend,
        ttl_seconds=int(otp_service.OTP_TTL.total_seconds()),
        resend_seconds=int(otp_service.RESEND_COOLDOWN.total_seconds()),
        max_attempts=otp_service.MAX_ATTEMPTS,
    )


@auth_bp.route('/verify/resend', methods=['POST'])
@limiter.limit("20 per hour")
def resend_otp():
    """Issue + push a new code for the pending signup (cooldown-guarded)."""
    user = _pending_verify_user()
    if user is None:
        payload = {'ok': False, 'status': 'no_pending',
                   'message': 'Pa gen kont an atant verifikasyon.',
                   'redirect': url_for('auth.register')}
        return jsonify(payload) if _wants_json() else redirect(url_for('auth.register'))

    from app.services import otp_service

    wait = otp_service.resend_wait(user.whatsapp)
    if wait:
        payload = {'ok': False, 'status': 'cooldown', 'wait': wait,
                   'message': f'Tann {wait} segond anvan ou mande yon lòt kòd.'}
        return jsonify(payload)

    _otp, delivered_via = otp_service.issue_and_send(
        user.whatsapp, user_id=user.id, ip_address=request.remote_addr
    )

    if delivered_via == 'dev_fallback':
        response = {
            'ok': True, 'delivered': delivered_via,
            'wait': int(otp_service.RESEND_COOLDOWN.total_seconds()),
            'message': 'Mod DEV: Pa gen founisè WhatsApp ki rive voye kòd la.',
            'dev_code': _otp.dev_code,
        }
        return jsonify(response)

    if delivered_via:
        return jsonify({
            'ok': True, 'delivered': delivered_via,
            'wait': int(otp_service.RESEND_COOLDOWN.total_seconds()),
            'message': 'Nou voye yon nouvo kòd sou WhatsApp ou.',
        })

    return jsonify({
        'ok': False, 'status': 'undelivered',
        'wait': int(otp_service.RESEND_COOLDOWN.total_seconds()),
        'message': ('Nou pa rive voye kòd la kounye a. Eseye ankò pita oswa '
                    'kontakte administrateur a.'),
    })


# IP-level limiter: relatively generous because it counts EVERY page view (GET)
# + attempts (POST) per IP. Behind a shared proxy (Render/Heroku), many users
# share one IP, so a tight limit (e.g. "10 per minute") falsely locks everyone out.
# Real brute-force protection is handled by the per-identifier custom limiter
# (5 failed logins / 5 min) inside this route.
@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("30 per minute")
def login():
    """User login — P1 bugfixes:
    - PRESERVE the `next` query param across GET → POST → FAIL redirect → success redirect.
      Before: `next` only in request.args but form action posted to bare /auth/login → lost.
    - PRESERVE the `identifier` submitted after FAIL redirect so user doesn't retype it.
    - Fix lost deep-link (from /ecole_biblique/module/1 → login → module1) forever.
    - Forbid open-redirect (url_has_allowed_host_and_scheme already used).
    """
    if current_user.is_authenticated:
        n = request.args.get('next')
        def _safe_top(u):
            if not u or not u.startswith('/') or u.startswith('//') or '://' in u:
                return False
            try:
                from werkzeug.urls import url_has_allowed_host_and_scheme as _uh
                return bool(_uh(u, request.host))
            except Exception:
                try:
                    from werkzeug.security import url_has_allowed_host_and_scheme as _uh
                    return bool(_uh(u, request.host))
                except Exception:
                    return ('javascript:' not in u.lower() and '<' not in u)
        if _safe_top(n):
            return redirect(n)
        return redirect(url_for('main.index'))

    # Resolve deep-link `next` from GET-args OR POST-form. Lasts across redirects.
    def _safe_next(u):
        """Check URL safe (open-redirect protection).
        Defensive import: werkzeug 2.x/3.x moved `url_has_allowed_host_and_scheme`
        to werkzeug.urls (NOT werkzeug.security). Fallback to basic heuristic on
        any ImportError (start with /, no //, no ://, no <script).
        """
        if not u:
            return False
        try:
            from werkzeug.urls import url_has_allowed_host_and_scheme as _uh
            return bool(_uh(u, request.host))
        except Exception:
            pass
        try:
            from werkzeug.security import url_has_allowed_host_and_scheme as _uh
            return bool(_uh(u, request.host))
        except Exception:
            pass
        return bool(
            u.startswith('/') and
            not u.startswith('//') and
            '://' not in u and
            'javascript:' not in u.lower() and
            '<' not in u
        )

    def _get_next():
        n = request.args.get('next') or request.form.get('next') or ''
        return n if _safe_next(n) else ''

    def _redirect_back_with_params(**extra):
        # Re-compose /auth/login?next=..&last_identifier=.. on every FAIL redirect.
        # Preserves deep-link + re-populates identifier after 302.
        q = {}
        nx = _get_next()
        if nx:
            q['next'] = nx
        q.update(extra)
        target = url_for('auth.login', **q) if q else url_for('auth.login')
        return redirect(target)

    if request.method == 'POST':
        try:
            identifier = request.form.get('identifier', '').strip()
            password = request.form.get('password', '').strip()
            remember = True  # SESSION FIX: always remember; session permanent=True below

            if not identifier or not password:
                flash('Tout chan yo obligatwa.', 'error')
                return _redirect_back_with_params(last_identifier=identifier)

            # Strict match only — NO substring LIKE (prevent takeover). Several
            # accounts can legitimately share one WhatsApp number, and only the
            # password says which one is meant, so resolve against the candidate
            # list instead of an arbitrary first row (see _find_users_by_identifier).
            candidates = _find_users_by_identifier(identifier)
            user = None
            for _cand in candidates:
                _ok = False
                try:
                    _ok = bool(_cand.check_password(password))
                except Exception:
                    _ok = False
                if not _ok:
                    _ok = bool(_check_forgot_temp_password(_cand.id, password))
                if _ok:
                    user = _cand
                    break

            if not user:
                # BUGFIX: rate-limit ONLY on actual failure (was counting successful logins).
                # _cache_identifier_rate_limit() both checks AND records in one call:
                #   returns True  → limit already reached (BLOCK, nothing recorded)
                #   returns False → attempt recorded, allow (with error message)
                if _cache_identifier_rate_limit("login_fail_id", identifier, 5, 300):
                    current_app.logger.warning(
                        "Login rate-limit BLOCKED for identifier=%s", identifier[:8] + "***",
                    )
                    flash(
                        '5 esè koneksyon invalide yo te pase. Tanpri tann 5 minit epi eseye ankò.',
                        'error',
                    )
                    return _redirect_back_with_params(last_identifier=identifier)
                current_app.logger.warning(
                    "Login failed: identifier=%s (%d strict candidate(s), none matched the password)",
                    identifier[:8] + "***", len(candidates),
                )
                flash(
                    '❌ WhatsApp oswa pseudo ou pa egziste, oswa modpas ou pa bon. '
                    'Tanpri tcheke yo oswa klike sou "Oubliye modpas?".',
                    'error',
                )
                return _redirect_back_with_params(last_identifier=identifier)

            # Check password OR valid temporary forgot-password token
            password_ok = False
            try:
                password_ok = bool(user.check_password(password))
            except Exception:
                password_ok = False
            if not password_ok:
                password_ok = bool(_check_forgot_temp_password(user.id, password))

            if not password_ok:
                # BUGFIX: rate-limit ONLY on actual failure (was counting successful logins).
                if _cache_identifier_rate_limit("login_fail_id", identifier, 5, 300):
                    current_app.logger.warning(
                        "Login rate-limit BLOCKED for identifier=%s", identifier[:8] + "***",
                    )
                    flash(
                        '5 esè koneksyon invalide yo te pase. Tanpri tann 5 minit epi eseye ankò.',
                        'error',
                    )
                    return _redirect_back_with_params(last_identifier=identifier)
                current_app.logger.warning(
                    "Login failed: user_id=%s pseudo=%s wrong password",
                    user.id, user.pseudo,
                )
                flash(
                    '❌ Modpas ou pa koresponn ak kont sa a. '
                    'Tanpri eseye ankò oswa itilize "Oubliye modpas?" pou resèt.',
                    'error',
                )
                return _redirect_back_with_params(last_identifier=identifier)

            if not user.is_active:
                # Two different situations share the is_active flag, and telling
                # them apart is what decides whether the user has a way out:
                #   * a signup that never finished WhatsApp verification
                #     -> send them back to the code screen (the password they
                #        just proved they own is what authorises this)
                #   * an account an administrator switched off
                #     -> keep the "contact administrator" dead end
                if _is_pending_signup(user):
                    session['pending_verify_uid'] = user.id
                    flash(
                        'Kont ou poko verifye. Tanpri antre kòd 6 chif nou voye '
                        'sou WhatsApp ou a pou aktive l.',
                        'info',
                    )
                    return redirect(url_for('auth.verify_phone'))
                flash('Kont ou an dezaktive. Kontakte administrateur a.', 'error')
                return _redirect_back_with_params(last_identifier=identifier)

            # If user used temp forgot pw, clear it so single-use only
            if _check_forgot_temp_password(user.id, password):
                try:
                    if cache:
                        cache.delete(_FORGOT_KEY.format(user.id))
                except Exception:
                    pass
                flash(
                    "Tanpri chanje modpas ou nan pwofil ou rapidman (modpas pwovizwa a itilize 1 fwa sèlman).",
                    "warning",
                )

            # BUGFIX: successful login — CLEAR the per-identifier failure counter
            try:
                if cache:
                    cache.delete(f"rl:login_fail_id:{identifier}")
            except Exception:
                pass

            # Login user, remember=always, force=True (bypass inactive check — already validated above)
            login_user(user, remember=True, force=True)

            from flask import session as _s
            _s.permanent = True
            _s['_remember_set'] = True

            user.last_login = datetime.utcnow()
            db.session.commit()

            flash(f'✅ Byenveni, {user.pseudo}! Ou konekte avèk siksè.', 'success')

            next_page = _get_next()
            if next_page:
                return redirect(next_page)
            return redirect(url_for('main.index'))

        except ValidationError as e:
            current_app.logger.warning("Login validation error: %s", e)
            flash(str(e), 'error')
            return _redirect_back_with_params()
        except Exception as e:
            import traceback
            current_app.logger.error(
                "Login exception: %s\n%s", e, traceback.format_exc(),
            )
            db.session.rollback()
            flash('Erè nan koneksyon. Tanpri eseye ankò.', 'error')
            return _redirect_back_with_params()

    # GET: expose next_value + last_identifier_value to template for hidden input + pre-fill
    next_value = _get_next()
    last_identifier = request.args.get('last_identifier', '').strip() or ''
    return render_template(
        'auth/login.html',
        next_value=next_value,
        last_identifier=last_identifier,
    )


@auth_bp.route('/login/otp/request', methods=['POST'])
@limiter.limit("10 per hour")
def login_otp_request():
    """Push a one-time login code to the WhatsApp number of an EXISTING account.

    This is a companion to :func:`login`, not a replacement: the password path
    stays exactly as it was, so a WhatsApp delivery outage can never lock someone
    out of an account they already hold. The identifier accepts the same
    pseudo-or-WhatsApp value as the password form (see :func:`_find_users_by_identifier`).
    """
    if current_user.is_authenticated:
        return jsonify({'ok': False, 'message': 'Ou deja konekte.'})

    identifier = (request.form.get('identifier') or '').strip()
    if not identifier:
        return jsonify({'ok': False, 'message': 'Tanpri antre WhatsApp ou oswa pseudo.'})

    if _cache_identifier_rate_limit('login_otp_id', identifier, 5, 900):
        current_app.logger.warning(
            'Login-OTP rate-limit BLOCKED for identifier=%s', identifier[:8] + '***')
        return jsonify({'ok': False, 'status': 'rate_limited',
                        'message': 'Twòp demann kòd. Tanpri tann 15 minit.'})

    # Only an ACTIVE account, and only one that actually owns a number, can be
    # reached this way — an OTP must never become a way around an admin block.
    user = None
    for cand in _find_users_by_identifier(identifier):
        if cand.is_active and cand.whatsapp:
            user = cand
            break

    if user is None:
        return jsonify({
            'ok': False, 'status': 'not_found',
            'message': 'Pa gen kont aktif ki koresponn ak idantifyan sa. '
                       'Tcheke ekriti a oswa kreye yon kont.',
        })

    from app.services import otp_service
    from app.models.otp import OtpCode

    wait = otp_service.resend_wait(user.whatsapp, OtpCode.PURPOSE_LOGIN)
    if wait:
        return jsonify({'ok': False, 'status': 'cooldown', 'wait': wait,
                        'message': f'Tann {wait} segond anvan ou mande yon lòt kòd.'})

    _otp, delivered_via = otp_service.issue_and_send(
        user.whatsapp, user_id=user.id,
        purpose=OtpCode.PURPOSE_LOGIN, ip_address=request.remote_addr,
    )

    if not delivered_via:
        # Honest failure: no gateway could reach that number. Point the user at
        # the password form they already have instead of a dead-end spinner.
        return jsonify({
            'ok': False, 'status': 'undelivered',
            'message': 'Nou pa rive voye kòd la kounye a. Tanpri konekte ak modpas ou.',
        })

    session['pending_login_otp_uid'] = user.id
    response = {
        'ok': True, 'delivered': delivered_via,
        'masked_phone': _mask_phone(user.whatsapp),
        'message': 'Nou voye yon kòd 6 chif sou WhatsApp ou.',
    }
    if delivered_via == 'dev_fallback':
        response['message'] = 'Mod DEV: Pa gen founisè WhatsApp ki rive voye kòd la.'
        response['dev_code'] = _otp.dev_code
    return jsonify(response)


@auth_bp.route('/login/otp/verify', methods=['POST'])
@limiter.limit("40 per hour")
def login_otp_verify():
    """Exchange a valid login code for a session. The password is never involved."""
    if current_user.is_authenticated:
        return jsonify({'ok': True, 'redirect': url_for('main.index')})

    uid = session.get('pending_login_otp_uid')
    if not uid:
        return jsonify({'ok': False, 'status': 'no_pending',
                        'message': 'Tanpri mande yon kòd anvan.'})

    try:
        user = db.session.get(User, int(uid))
    except (TypeError, ValueError):
        user = None

    if user is None or not user.is_active or not user.whatsapp:
        session.pop('pending_login_otp_uid', None)
        return jsonify({'ok': False, 'status': 'unavailable',
                        'message': 'Kont sa a pa disponib ankò. Tanpri rekòmanse.'})

    from app.services import otp_service
    from app.models.otp import OtpCode

    status, _row = otp_service.verify(
        user.whatsapp, request.form.get('code', ''), purpose=OtpCode.PURPOSE_LOGIN)
    st = otp_service.state(user.whatsapp, OtpCode.PURPOSE_LOGIN)

    if status != otp_service.OK:
        messages = {
            otp_service.WRONG: 'Kòd la pa kòrèk. Eseye ankò.',
            otp_service.EXPIRED: 'Kòd la ekspire. Tanpri mande yon lòt.',
            otp_service.LOCKED: 'Twòp tantativ. Tanpri mande yon nouvo kòd.',
            otp_service.MISSING: 'Tanpri antre kòd 6 chif la.',
        }
        return jsonify({
            'ok': False, 'status': status,
            'message': messages.get(status, 'Kòd la pa valide.'),
            'attempts_left': st.get('attempts_left', 0),
            'resend_in': st.get('resend_in', 0),
        })

    login_user(user, remember=True, force=True)
    session.permanent = True
    session['_remember_set'] = True
    session.pop('pending_login_otp_uid', None)

    try:
        if cache:
            cache.delete(f'rl:login_otp_id:{user.pseudo}')
            cache.delete(f'rl:login_otp_id:{user.whatsapp}')
    except Exception:
        pass

    user.last_login = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'ok': True,
        'message': f'Byenveni, {user.pseudo}! Ou konekte avèk siksè.',
        'redirect': url_for('main.index'),
    })


@auth_bp.route('/logout')
def logout():
    """User logout — properly clears the remember-me cookie.

    CRITICAL FIX: Flask-Login 0.6.x sets session['_remember'] = 'clear' inside
    logout_user() to signal that the remember-me cookie must be deleted when the
    response is finalised. The old code called session.clear() right after, which
    erased that marker — so the 1-year cookie stayed in the browser and the very
    next request silently re-logged the same account back in. That is exactly the
    "I have to create a new account after logging out" report.

    Fix: preserve the '_remember' marker AND the CSRF token through the clear.
    """
    logout_user()                          # sets session['_remember'] = 'clear'
    remember_marker = session.get('_remember')   # capture BEFORE clear
    csrf_token      = session.get('_csrf_token')
    session.clear()
    if remember_marker:                    # restore so Flask-Login can delete the cookie
        session['_remember'] = remember_marker
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
    from app.utils.validators import ValidationError
    try:
        ads = AdService.get_user_ads(current_user.whatsapp)
    except ValidationError as e:
        flash(
            "Nimewo WhatsApp kont ou pa konfigire byen: %s. Kontakte admin yo pou repare." % str(e),
            "error",
        )
        ads = []
    except Exception as e:
        current_app.logger.error("my_ads unexpected error for user %s: %s", current_user.id, e)
        flash("Erè nan chaj piblisite ou yo.", "error")
        ads = []
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
            quantity = request.form.get('quantity', None)
            if quantity is not None and quantity != '':
                try:
                    quantity = int(quantity)
                except (ValueError, TypeError):
                    quantity = None

            AdService.update_ad(
                ad_id=ad_id,
                user_whatsapp=current_user.whatsapp,
                title=title,
                description=description,
                price_gkach=price_gkach,
                quantity=quantity
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
