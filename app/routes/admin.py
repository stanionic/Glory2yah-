"""
Admin Routes Blueprint
Management of ads, users, batches, and transactions
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session, current_app, make_response
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
import io as _io


admin_bp = Blueprint('admin', __name__)


# ============================================================================
# ADMIN QR CODE SIGNED URL (HMAC-SHA256 + SECRET_KEY, 7-day expiry)
# Stores credentials securely (server-signed, cannot be tampered) inside QR.
# Scanning QR → opens /admin/login?qra=<token> → fields auto-filled + green
# CTA "Se connecter maintenant (QR)".
# ============================================================================

_QRA_VALID_SECONDS = 7 * 24 * 3600  # 7 days (re-print each week for PROD)

def _qra_get_creds_from_config():
    """Return (identifier, password) tuple for admin. Never None (fallbacks)."""
    cfg = current_app.config
    _id = (cfg.get('ADMIN_PSEUDO')
           or cfg.get('ADMIN_WHATSAPP')
           or '+50942882076')
    _pw = (cfg.get('ADMIN_PASSWORD')
           or 'StanGlory2YahPub1986')
    return str(_id), str(_pw)


def _qra_get_admin_creds_full():
    """Return dict with all admin credentials for display. Never None (fallbacks)."""
    cfg = current_app.config
    _id, _pw = _qra_get_creds_from_config()
    return {
        'name': str(cfg.get('ADMIN_NAME') or 'Glory2YahPub'),
        'whatsapp': str(cfg.get('ADMIN_WHATSAPP') or '+50942882076'),
        'pseudo': _id,
        'password': _pw,
    }


def _qra_signing_key():
    """Derive a stable signing key from SECRET_KEY (salted)."""
    sk = current_app.config.get('SECRET_KEY') or 'glory2yah-dev-fallback-secret-key-change-in-prod'
    salt = 'g2yah-qrauth-v1|'
    return (salt + str(sk)).encode('utf-8')


def _qra_make_signed_url(_external=True):
    """Build `/admin/login?qra=<signed>` URL. HMAC of (id, pw, exp_utc)."""
    import hmac as _hm, hashlib as _hl, base64 as _b64, json as _js, time as _tm
    admin_id, admin_pw = _qra_get_creds_from_config()
    exp = int(_tm.time()) + _QRA_VALID_SECONDS
    payload = {
        'v': 1,
        'id': admin_id,
        'pw': admin_pw,
        'e': exp,
    }
    msg_b = _js.dumps(payload, separators=(',', ':')).encode('utf-8')
    sig = _hm.new(_qra_signing_key(), msg_b, _hl.sha256).digest()
    # Bundle: b64(msg_b) . b64(sig)  (URL-safe base64, no padding)
    def _b64u(b):
        return _b64.urlsafe_b64encode(b).rstrip(b'=').decode('ascii')
    token = _b64u(msg_b) + '.' + _b64u(sig)
    return url_for('admin.admin_login', qra=token, _external=_external)


def _qra_verify_signed(token):
    """Verify ?qra= token. Returns dict {id, pw, exp} on success, else None."""
    import hmac as _hm, hashlib as _hl, base64 as _b64, json as _js, time as _tm
    if not token or '.' not in token:
        return None
    try:
        msg_part, sig_part = str(token).split('.', 1)
        def _b64ud(s):
            pad = '=' * (-len(s) % 4)
            return _b64.urlsafe_b64decode(s + pad)
        msg_b = _b64ud(msg_part)
        sig = _b64ud(sig_part)
        # constant-time compare
        expected = _hm.new(_qra_signing_key(), msg_b, _hl.sha256).digest()
        if not _hm.compare_digest(expected, sig):
            return None
        data = _js.loads(msg_b.decode('utf-8'))
        if int(data.get('v', 0)) != 1:
            return None
        if int(data.get('e', 0)) < int(_tm.time()):
            return None
        if not data.get('id') or not data.get('pw'):
            return None
        return {'id': str(data['id']), 'pw': str(data['pw']), 'exp': int(data['e'])}
    except Exception:
        return None


def _make_admin_qr_png_bytes(scale=6, dark=(58, 38, 128)):
    """Return PNG bytes for a QR code linking to the SIGNED /admin/login?qra=
    URL (credentials embedded + HMAC-signed, 7-day expiry)."""
    admin_signed_url = _qra_make_signed_url(_external=True)
    try:
        import segno  # type: ignore
        qr = segno.make(admin_signed_url, error='M')
        buf = _io.BytesIO()
        qr.save(buf, kind='png', scale=scale, dark=dark, light=(255, 255, 255), border=2)
        return buf.getvalue()
    except Exception:
        return b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xcf\xc0\xff\xff?\x03\x00\x06\x05\x02\xfe\xc7\xe5\x8d\xa4\x00\x00\x00\x00IEND\xaeB`\x82'


@admin_bp.route('/qr.png')
@login_required
@admin_required
def admin_qr_png():
    """PNG endpoint: GET /admin/qr.png → admin QR SIGNED URL (cache 1 min).
    ACCESS: Admin authenticated ONLY. Returns 302 to login for anon + 403 for non-admin users."""
    data = _make_admin_qr_png_bytes(scale=6, dark=(58, 38, 128))
    resp = make_response(data)
    resp.headers['Content-Type'] = 'image/png'
    resp.headers['Content-Disposition'] = 'inline; filename="admin_login_qr_signed.png"'
    resp.headers['Cache-Control'] = 'private, max-age=60'
    resp.headers['Content-Length'] = str(len(data))
    return resp


@admin_bp.route('/qr')
@login_required
@admin_required
def admin_qr_page():
    """Pretty card with signed QR.
    ACCESS: Admin authenticated ONLY. No credentials leaked publicly.
    Shows QR image + download copy controls; never shows id/pw strings in HTML."""
    admin_signed_url = _qra_make_signed_url(_external=True)
    admin_creds = _qra_get_admin_creds_full()
    return render_template(
        'admin_qr.html',
        admin_login_url=admin_signed_url,
        qr_signed=True,
        qr_valid_days=(_QRA_VALID_SECONDS // (24 * 3600)),
        admin_creds=admin_creds,
    )


@admin_bp.route('/login', methods=['GET', 'POST'])
def admin_login():
    """Dedicated admin login page.

    Supports QR-signed deep link via ?qra=<HMAC-signed-token>:
      - HMAC verified + not expired → identifier & password pre-filled,
        badge "🛡️ QR Credentials chargés" shown, green CTA button enabled.
      - Otherwise → regular empty login form (backwards-compatible).
    """
    from flask_login import login_user, current_user
    if current_user.is_authenticated and current_user.is_admin:
        return redirect(url_for('admin.dashboard'))

    if request.method == 'POST':
        pseudo = request.form.get('pseudo', '').strip()
        password = request.form.get('password', '').strip()

        # Robust 4-tier identifier lookup (exact parity with /auth/login _find_user_by_identifier).
        # Supports: pseudo / WhatsApp with-or-without + / pseudo case-insensitive (Admin509/admin509/ADMIN509).
        def _clean_wa(raw: str) -> str:
            raw = (raw or '').strip()
            cleaned = ''.join(c for c in raw if c.isdigit() or c == '+')
            if cleaned and not cleaned.startswith('+'):
                cleaned = '+' + cleaned
            return cleaned or raw

        user = None
        ident = pseudo or ''
        clean_wa = _clean_wa(ident)
        # 1 exact raw (pseudo == ident OR whatsapp == ident)
        if ident:
            user = User.query.filter(
                db.or_(User.pseudo == ident, User.whatsapp == ident)
            ).first()
        # 2 cleaned (different from raw, i.e. user typed spaces/letters -> WA-like number)
        if (not user) and clean_wa != ident and clean_wa:
            user = User.query.filter(
                db.or_(User.pseudo == clean_wa, User.whatsapp == clean_wa)
            ).first()
        # 3 pseudo case-insensitive (using cleaned_wa if looks WA-like)
        if (not user) and clean_wa:
            user = User.query.filter(
                db.func.lower(User.pseudo) == clean_wa.lower()
            ).first()
        # 4 pseudo case-insensitive (using RAW identifier — catches ADMIN509/admin509
        #   whenever _clean_wa stripped letters from a text pseudo!)
        if (not user) and ident:
            user = User.query.filter(
                db.func.lower(User.pseudo) == ident.lower()
            ).first()

        if not user:
            flash('Pseudo oswa modpas envalid.', 'error')
        elif not getattr(user, 'is_active', True):
            # Mirror /auth/login guard: blocked (is_active=False) users CANNOT login even via admin portal
            flash('Kont itilizatè sa a dezaktive / bloke. Kontakte admin yo.', 'error')
        elif not user.is_admin:
            flash('Kont sa a pa yon kont administrateur.', 'error')
        elif user.check_password(password):
            login_user(user)
            flash('Byenveni Administratè!', 'success')
            return redirect(url_for('admin.dashboard'))
        else:
            flash('Pseudo oswa modpas envalid.', 'error')

    # GET: handle ?qra= signed token → auto-fill (silent on invalid)
    auto_id = ''
    auto_pw = ''
    qr_valid = False
    qr_exp = None
    qra_token = request.args.get('qra', '') or request.form.get('qra', '')
    if qra_token:
        v = _qra_verify_signed(qra_token)
        if v:
            auto_id = v['id']
            auto_pw = v['pw']
            qr_valid = True
            qr_exp = v['exp']

    return render_template(
        'admin_login.html',
        auto_id=auto_id,
        auto_pw=auto_pw,
        qr_valid=qr_valid,
        qr_exp=qr_exp,
        qra_token=qra_token,
    )


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
    
    # Resolve the promotional (demo) video URL.
    # If an admin has uploaded a custom promo video it lives in static/uploads/
    # (filenames stored in AdminSettings 'demo_video'); otherwise fall back to
    # the default static/glory2yahpub_demo.mp4.
    demo_video_name = AdminSettings.get_setting('demo_video', None)
    if demo_video_name:
        demo_video_url = url_for('static', filename='uploads/' + str(demo_video_name))
    else:
        demo_video_url = url_for('static', filename='glory2yahpub_demo.mp4')
    
    return render_template(
        'admin.html',
        stats=stats,
        ads=ads,
        batches=batches,
        users_gkach=users_gkach,
        admin_settings=admin_settings,
        demo_video_url=demo_video_url,
        demo_video_name=demo_video_name,
        current_user=current_user
    )


@admin_bp.route('/demo-video/update', methods=['POST'])
@login_required
@admin_required
def update_demo_video():
    """Update the app's PROMOTIONAL video (the video that explains what the
    app does / promotes Glory2YahPub). Uploaded file is saved to static/uploads/
    and its filename stored in AdminSettings ('demo_video') so the admin card,
    download/share buttons and the /demo page all use the new video."""
    import os
    import uuid

    try:
        if 'demo_video' not in request.files:
            flash('Tanpri chwazi yon videyo pou telechaje.', 'error')
            return redirect(url_for('admin.dashboard'))

        file = request.files['demo_video']
        if not file or not file.filename:
            flash('Tanpri chwazi yon videyo pou telechaje.', 'error')
            return redirect(url_for('admin.dashboard'))

        ext = (
            file.filename.rsplit('.', 1)[-1].lower()
            if '.' in file.filename else 'mp4'
        )
        allowed = current_app.config.get('ALLOWED_VIDEO_EXTENSIONS', {'mp4','avi','mov','mkv','webm'})
        if ext not in allowed:
            flash(
                f'Tip videyo a pa aksepte. Aksepte sèlman: {", ".join(sorted(allowed)).upper()}.',
                'error'
            )
            return redirect(url_for('admin.dashboard'))

        # Size guard (100MB max, matching MAX_CONTENT_LENGTH)
        file.seek(0, 2)
        video_bytes = file.tell()
        file.seek(0)
        max_bytes = int(current_app.config.get('MAX_CONTENT_LENGTH', 100*1024*1024))
        if video_bytes > max_bytes:
            flash(f'Videyo a twò gwo (≈{round(video_bytes/1024/1024,1)} MB). Maksimòm otorize: {max_bytes//1024//1024} MB.', 'error')
            return redirect(url_for('admin.dashboard'))

        # Save to static/uploads/ (persistent disk on Render)
        upload_folder = os.path.join(
            current_app.root_path, '..', current_app.config['UPLOAD_FOLDER']
        )
        upload_folder = os.path.abspath(upload_folder)
        os.makedirs(upload_folder, exist_ok=True)

        filename = f'promo_{uuid.uuid4().hex}.{ext}'
        dest_path = os.path.join(upload_folder, filename)
        file.save(dest_path)

        # Store reference in AdminSettings
        AdminSettings.set_setting('demo_video', filename)

        flash(
            '✅ Videyo Pwomosyonèl mete ajou avèk siksè! '
            'Kounye a li itilize pou pwomouvwa app la (paj /demo, pataj, telechajman).',
            'success'
        )
    except Exception as e:
        current_app.logger.error(f"Admin update_demo_video failed: {e}")
        flash('Erè pandan mete ajou videyo pwomosyonèl la.', 'error')

    return redirect(url_for('admin.dashboard'))


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


@admin_bp.route('/audit')
@login_required
@admin_required
def audit_logs():
    """Show the last 150 audit log entries (Ecole Biblique ecole_audit_logs)."""
    page = request.args.get('page', 1, type=int)
    per_page = 50
    try:
        from ecole_biblique.models import AuditLog as EAB
        q_total = EAB.query.count()
        entries = (EAB.query
                   .order_by(EAB.created_at.desc())
                   .limit(150)
                   .all())
        # small pagination
        start = (page - 1) * per_page
        end = start + per_page
        page_rows = entries[start:end]
        total_pages = max(1, (len(entries) + per_page - 1) // per_page)
        actions_summary = {}
        for e in entries:
            actions_summary[e.action] = actions_summary.get(e.action, 0) + 1
    except Exception as exc:
        page_rows = []
        q_total = 0
        total_pages = 1
        actions_summary = {}
        current_app.logger.warning(f'audit_logs: load failed {type(exc).__name__}: {exc}')
    return render_template(
        'admin_audit.html',
        rows=page_rows,
        page=page,
        per_page=per_page,
        total=q_total,
        total_pages=total_pages,
        top_actions=actions_summary,
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


@admin_bp.route('/users/<int:user_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_user_status(user_id):
    """Toggle is_active for a user (Block/Unblock in 1 click).
    Admin cannot block/unblock themselves."""
    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash('Ou pa ka bloke oswa debloke tèt ou menm!', 'error')
        return redirect(url_for('admin.manage_users'))

    user.is_active = not user.is_active
    db.session.commit()

    action = 'bloke' if not user.is_active else 'debloke'
    flash(f'Kont "{user.pseudo or user.whatsapp}" {action} avèk siksè!', 'success')
    return redirect(url_for('admin.manage_users'))


@admin_bp.route('/users/block-by-pseudo', methods=['POST'])
@login_required
@admin_required
def block_user_by_pseudo():
    """Block a user account by their pseudo (from the DB).
    Pseudo search is case-insensitive. Safely blocks the account."""
    pseudo = request.form.get('pseudo', '').strip()

    if not pseudo:
        flash('Tanpri antre yon pseudo pou bloke.', 'error')
        return redirect(url_for('admin.manage_users'))

    user = User.query.filter(User.pseudo.ilike(pseudo)).first()

    if not user:
        flash(f'Pseudo "{pseudo}" pa jwenn nan baz done a.', 'error')
        return redirect(url_for('admin.manage_users'))

    if user.id == current_user.id:
        flash('Ou pa ka bloke tèt ou menm!', 'error')
        return redirect(url_for('admin.manage_users'))

    if not user.is_active:
        flash(f'Kont "{user.pseudo}" deja bloke.', 'info')
        return redirect(url_for('admin.manage_users'))

    user.is_active = False
    db.session.commit()
    flash(f'Kont "{user.pseudo}" bloke avèk siksè! Li pa ka konekte ankò.', 'success')
    return redirect(url_for('admin.manage_users'))


@admin_bp.route('/rewards')
@login_required
@admin_required
def rewards():
    """Admin rewards dashboard — shows UNIQUE clicks and Admin rewards paid
    per sharer (referrer) per shared batch link.

    Rules reflected here:
      - Each click counts once per unique person (BatchClick unique constraint).
      - The platform/Admin pays +GKACH_REWARD_AMOUNT (10) Gkach every
        GKACH_CLICKS_REQUIRED (100) unique clicks to each sharer (referrer).
      - Actually PAID rewards = GkachTransaction rows of type 'reward'.
    """
    from sqlalchemy import func
    from app.models.batch import Batch
    from app.models.batch_click import BatchClick
    from app.models.gkach_transaction import GkachTransaction
    from app.models.user import User

    required = int(current_app.config.get('GKACH_CLICKS_REQUIRED', 100) or 100)
    reward = int(current_app.config.get('GKACH_REWARD_AMOUNT', 10) or 10)

    # Aggregate UNIQUE clicks per (batch, referrer)
    rows = (
        db.session.query(
            BatchClick.batch_id,
            BatchClick.referrer_whatsapp,
            func.count(BatchClick.id).label('unique_clicks'),
            func.count(func.distinct(BatchClick.clicker_ip)).label('unique_ips'),
            func.max(BatchClick.created_at).label('last_click'),
        )
        .group_by(BatchClick.batch_id, BatchClick.referrer_whatsapp)
        .order_by(func.max(BatchClick.created_at).desc())
        .all()
    )

    # Map batch_id -> Batch for labels
    batch_ids = {r.batch_id for r in rows}
    batches_map = {
        b.batch_id: b for b in Batch.query.filter(Batch.batch_id.in_(batch_ids)).all()
    } if batch_ids else {}

    # Map referrer -> user info
    referrers = {r.referrer_whatsapp for r in rows}
    users_map = {
        u.whatsapp: u for u in User.query.filter(User.whatsapp.in_(referrers)).all()
    } if referrers else {}

    # Map actually paid rewards per (referrer, batch) from GkachTransaction
    reward_txns = GkachTransaction.query.filter_by(
        transaction_type='reward', status='completed'
    ).all()
    paid_map = {}  # (referrer, batch_id) -> {'txns': int, 'amount': int}
    for t in reward_txns:
        # Description format: "Rekonpans Admin: +10 Gkach pou 100 klik inik sou batch <id>"
        bid = None
        if t.ad_id:  # optional ad reference
            bid = str(t.ad_id)
        else:
            idx = t.description.find('batch ')
            if idx != -1:
                bid = t.description[idx + len('batch '):].strip()
        if bid:
            key = (t.user_whatsapp, bid)
            e = paid_map.setdefault(key, {'txns': 0, 'amount': 0})
            e['txns'] += 1
            e['amount'] += t.amount

    entries = []
    for r in rows:
        clicks = r.unique_clicks
        milestones = clicks // required
        expected = milestones * reward
        key = (r.referrer_whatsapp, r.batch_id)
        paid = paid_map.get(key, {'txns': 0, 'amount': 0})
        batch = batches_map.get(r.batch_id)
        user = users_map.get(r.referrer_whatsapp)
        entries.append({
            'batch_id': r.batch_id,
            'referrer_whatsapp': r.referrer_whatsapp,
            'pseudo': (user.pseudo if user else None) or r.referrer_whatsapp,
            'unique_clicks': clicks,
            'unique_ips': r.unique_ips or 0,
            'milestones': milestones,
            'expected_reward': expected,
            'paid_txns': paid['txns'],
            'paid_amount': paid['amount'],
            'progress': clicks % required,          # clicks toward next milestone
            'next_milestone': required - (clicks % required),
            'last_click': r.last_click,
            'ads_count': batch.batch_ads.count() if batch else 0,
        })

    entries.sort(key=lambda e: e['unique_clicks'], reverse=True)

    # Load currently blocked IPs (managed by the admin)
    blocked_ips = GkachService.get_blocked_ips()

    return render_template(
        'admin_rewards.html',
        entries=entries,
        required=required,
        reward=reward,
        blocked_ips=blocked_ips,
        current_user=current_user,
    )


@admin_bp.route('/rewards/block-ip', methods=['POST'])
@login_required
@admin_required
def block_ip():
    """Block a client IP from contributing clicks/rewards (anti-fraud).

    Stored as a comma/newline separated list in AdminSettings
    under the key 'blocked_ips'; checked by GkachService._is_ip_blocked.
    """
    raw_ip = (request.form.get('ip') or '').strip()
    if not raw_ip:
        flash('Antre yon adrès IP pou bloke.', 'error')
        return redirect(url_for('admin.rewards'))

    blocked_ips = GkachService.get_blocked_ips()
    if raw_ip not in blocked_ips:
        blocked_ips.append(raw_ip)
        GkachService.set_blocked_ips(blocked_ips)
        flash(f'Adrès IP {raw_ip} bloke avèk siksè!', 'success')
    else:
        flash(f'Adrès IP {raw_ip} te deja bloke.', 'info')

    return redirect(url_for('admin.rewards'))


@admin_bp.route('/rewards/unblock-ip', methods=['POST'])
@login_required
@admin_required
def unblock_ip():
    """Remove a previously blocked IP."""
    raw_ip = (request.form.get('ip') or '').strip()
    if not raw_ip:
        flash('Antre yon adrès IP pou debloke.', 'error')
        return redirect(url_for('admin.rewards'))

    blocked_ips = GkachService.get_blocked_ips()
    if raw_ip in blocked_ips:
        blocked_ips = [ip for ip in blocked_ips if ip != raw_ip]
        GkachService.set_blocked_ips(blocked_ips)
        flash(f'Adrès IP {raw_ip} debloke avèk siksè!', 'success')
    else:
        flash(f'Adrès IP {raw_ip} pa nan lis bloke yo.', 'info')

    return redirect(url_for('admin.rewards'))


@admin_bp.route('/ads')
@login_required
@admin_required
def manage_ads():
    """Manage all ads.

    Redirects to the admin dashboard (/admin/) which already includes:
    - Full ad review grid (approve/reject/verify payment/delete/contact)
    - Batch management (create groups of 5 approved ads)
    - Gkach management, QR admin login, popup settings, Facebook tests, demo video

    The previous implementation rendered admin.html with only `ads` and
    `current_user`, causing Jinja UndefinedError ('admin_settings' is
    undefined, 'batches' is undefined, 'users_gkach' is undefined) and
    therefore HTTP 500 Internal Server Error on Render. Also, the data
    source was incorrectly limited to *approved* ads only
    (`AdService.get_approved_ads`), while the dashboard properly uses
    `Ad.query.all()` so admins can *review* pending ads too.
    """
    return redirect(url_for('admin.dashboard'))


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
        current_app.logger.error(f"Admin ad_detail failed for ad_id={ad_id}: {e}")
        flash('Piblisite sa a pa jwenn.', 'error')
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
        current_app.logger.error(f"Admin approve_ad failed for ad_id={ad_id}: {e}")
        return jsonify({'success': False, 'message': 'Erè nan apwouve piblisite a.'}), 400


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
    except ValidationError as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"Admin reject_ad failed for ad_id={ad_id}: {e}")
        return jsonify({'success': False, 'message': 'Erè nan rejete piblisite a.'}), 400


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
                delta = new_balance - old_balance
                # P1 FIX: utiliser helpers add/deduct (thread-safe, CheckConstraint respecté, logs auto via GkachTransaction)
                if delta > 0:
                    GkachService.add_balance(
                        user_whatsapp,
                        delta,
                        f"Admin edit balance from {old_balance} to {new_balance}",
                        'admin_credit'
                    )
                elif delta < 0:
                    try:
                        GkachService.deduct_balance(
                            user_whatsapp,
                            abs(delta),
                            f"Admin edit balance from {old_balance} to {new_balance}",
                            'admin_debit'
                        )
                    except ValidationError as ve:
                        flash(f'Impossible de débiter: {str(ve)}', 'error')
                        return redirect(url_for('admin.manage_gkach'))
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
        current_app.logger.error(f"Admin create_batch failed: {e}")
        flash('Erè pandan kreyasyon pakèt piblisite a.', 'error')

    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/api/popup_settings', methods=['GET'])
@login_required
@admin_required
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
    """Update ad admin status and payment status.

    Supports three call patterns from the admin panel:

    1. MANUAL COMBO (2 dropdowns + "Mete Ajou" submit button) — legacy:
          status         = 'under_review' | 'approved' | 'rejected'
          payment_status = 'pending'      | 'verified' | 'rejected'

    2. ONE-CLICK ✅ "Apwouve Direkman" — most common admin action (2026-08-07):
          action = 'approve-direct'
       → Sets BOTH payment_status='verified' AND admin_status='approved' in one click.
         Also stamps publish_fee_gkach = 1000 (legacy compat for pre-fee rows).
         The manual fee-guard (needs payment verified) is BYPASSED because the admin
         explicitly clicked "Approve DIRECT" (= admin confirms payment received OK).

    3. ONE-CLICK ❌ "Rejte Direkman":
          action = 'reject-direct'
       → Sets admin_status='rejected' (and a default reason if none supplied).
    """
    ad_id        = request.form.get('ad_id')
    admin_status = request.form.get('status')
    payment_status = request.form.get('payment_status')
    action       = (request.form.get('action') or '').strip().lower()
    reason       = request.form.get('reason', '') or ''

    if not ad_id:
        flash('ID piblisite obligatwa.', 'error')
        return redirect(url_for('admin.dashboard'))

    ad = Ad.query.filter_by(ad_id=ad_id).first()
    if not ad:
        flash('Piblisite pa jwenn.', 'error')
        return redirect(url_for('admin.dashboard'))

    fee = int(getattr(ad, 'publish_fee_gkach', None) or 1000)
    skip_fee_guard = False

    # ---------- ONE-CLICK ACTIONS ----------
    if action == 'approve-direct':
        # Admin explicitly confirms: this ad is paid for → auto-flip BOTH flags.
        payment_status = 'verified'
        admin_status   = 'approved'
        skip_fee_guard = True
    elif action == 'reject-direct':
        payment_status = payment_status or ad.payment_status or 'pending'
        admin_status   = 'rejected'
        skip_fee_guard = True

    # ---------- STAMP DEFAULT FEE (legacy compat rows) ----------
    if not getattr(ad, 'publish_fee_gkach', None) or ad.publish_fee_gkach <= 0:
        try:
            setattr(ad, 'publish_fee_gkach', fee)
        except Exception:
            pass

    # ---------- FEE GUARD (only for manual "approved" status flip) ----------
    pay_ok = (ad.payment_status or '') in {'verified', 'completed'}
    if admin_status == 'approved' and not pay_ok and not skip_fee_guard:
        flash(
            '⚠️  PA KA METE APWOUVE TOUT SEL: Pèman an poko verifye!\n'
            '  👉 Ou gen 2 opsyon:\n'
            f'  (A) KLKE BOUTON VERT ✅ "Apwouve Direkman" anba a (pi fasil, 1 klik)\n'
            '  (B) Oubien manèlman: nan meni "Pèman Verifye" chwazi → klike Mete Ajou → '
            ' Apre sa, nan meni Estati chwazi "Apwouve" → klike Mete Ajou yon dezyèm fwa.\n'
            f'  💡 Frai piblikasyon = {fee} Gkach.',
            'error'
        )
        return redirect(url_for('admin.dashboard'))

    # ---------- APPLY CHANGES ----------
    changed_msg_parts = []
    if admin_status and ad.admin_status != admin_status:
        ad.admin_status = admin_status
        label = {'under_review': 'An Revizyon',
                 'approved':    '✅ Apwouve',
                 'rejected':    '❌ Rejte'}.get(admin_status, admin_status)
        changed_msg_parts.append(f'Estati admin → {label}')

    if payment_status and ad.payment_status != payment_status:
        ad.payment_status = payment_status
        label = {'pending':   'Pèman an Atann',
                 'verified':  '💳 Pèman Verifye',
                 'completed': '💳 Pèman Verifye',
                 'rejected':  'Pèman Rejte'}.get(payment_status, payment_status)
        changed_msg_parts.append(f'Estati pèman → {label}')

    if reason:
        # Save rejection reason onto the ad if column exists (legacy compat ignore)
        try:
            if hasattr(ad, 'reject_reason'):
                ad.reject_reason = reason[:500]
                if 'Rejte' in label or admin_status == 'rejected':
                    changed_msg_parts.append(f'Rezon: {reason[:80]}')
        except Exception:
            pass

    db.session.commit()

    # ---------- INVALIDATE CACHE ----------
    from app.services.redis_service import RedisService
    from app import redis_client
    try:
        RedisService(redis_client).invalidate_approved_ads()
        RedisService(redis_client).cache_delete(f"ad:{ad_id}")
    except Exception:
        pass

    # ---------- FLASH USER-FRIENDLY SUMMARY ----------
    if action == 'approve-direct':
        flash(
            f'✅ Piblisite "{(ad.title or ad.ad_id)[:45]}" APWOUVE avèk siksè!\n'
            f'   • Pèman verifye otomatik ({fee} Gkach)\n'
            f'   • Kounye a li parèt nan 🛒 Mache si ad_type = VANN\n'
            f'   • Li parèt tou nan fil d\'aktyalite / feed.',
            'success'
        )
    elif action == 'reject-direct':
        flash(f'❌ Piblisite "{(ad.title or ad.ad_id)[:45]}" rejete.', 'info')
    elif changed_msg_parts:
        flash(f'✓ Estati aktyalize avèk siksè: ' + ' | '.join(changed_msg_parts), 'success')
    else:
        flash('Ok — pa gen okenn chanjman detekte.', 'info')

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
        current_app.logger.error(f"Admin delete_ad failed for ad_id={ad_id}: {e}")
        flash('Erè pandan efase piblisite a.', 'error')
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
        current_app.logger.error(f"Admin mobile_config_update failed: {e}")
        flash('Erè pandan konfigirasyon aplikasyon mobil la.', 'error')
    
    return redirect(url_for('admin.mobile_config'))


# ═══════════════════════════════════════════
# CHARITY DONATION ADMIN ROUTES
# ═══════════════════════════════════════════

@admin_bp.route('/charity/donations')
@login_required
@admin_required
def charity_donations():
    """View all charitable donations"""
    from app.models.charity import CharityDonation, CharityCause
    from sqlalchemy import func
    
    # Get all donations ordered by date
    donations = CharityDonation.query.order_by(CharityDonation.created_at.desc()).all()
    
    # Calculate stats
    total_gkach = sum(d.amount_gkach for d in donations if d.status == 'completed') or 0
    total_donations = len(donations)
    total_donors = len(set(d.donor_whatsapp for d in donations if d.donor_whatsapp))
    
    # Breakdown by cause
    cause_totals = db.session.query(
        CharityDonation.cause,
        func.sum(CharityDonation.amount_gkach).label('total')
    ).filter(
        CharityDonation.status == 'completed'
    ).group_by(CharityDonation.cause).all()
    
    max_total = max([c.total for c in cause_totals], default=0)
    cause_breakdown = []
    for ct in cause_totals:
        percentage = int((ct.total / max_total * 100)) if max_total > 0 else 0
        cause_breakdown.append({
            'cause': ct.cause,
            'total': ct.total,
            'percentage': percentage
        })
    
    stats = {
        'total_gkach': total_gkach,
        'total_donations': total_donations,
        'total_donors': total_donors
    }
    
    # Get all charity causes
    causes = CharityCause.query.all()
    
    donation_data = [d.to_dict() for d in donations]
    
    return render_template(
        'admin_charity_donations.html',
        donations=donation_data,
        stats=stats,
        cause_breakdown=cause_breakdown,
        causes=causes,
        current_user=current_user
    )


@admin_bp.route('/charity/causes/add', methods=['POST'])
@login_required
@admin_required
def add_charity_cause():
    """Add a new charitable cause"""
    from app.models.charity import CharityCause
    import uuid
    
    try:
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        icon = request.form.get('icon', '❤️').strip()
        
        if not name:
            flash('Non kòz la obligatwa.', 'error')
            return redirect(url_for('admin.charity_donations'))
        
        cause = CharityCause(
            cause_id=str(uuid.uuid4()),
            name=name,
            description=description,
            icon=icon,
            is_active=True
        )
        db.session.add(cause)
        db.session.commit()
        flash(f'Kòz "{name}" kreye avèk siksè!', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Admin add_charity_cause failed cause={name!r}: {e}")
        flash('Erè pandan kreyasyon kòz charite a.', 'error')
    
    return redirect(url_for('admin.charity_donations'))


@admin_bp.route('/charity/causes/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_charity_cause():
    """Toggle active status of a charitable cause"""
    from app.models.charity import CharityCause
    
    try:
        cause_id = request.form.get('cause_id')
        cause = CharityCause.query.filter_by(cause_id=cause_id).first()
        if not cause:
            flash('Kòz pa jwenn.', 'error')
            return redirect(url_for('admin.charity_donations'))
        
        cause.is_active = not cause.is_active
        db.session.commit()
        flash(f'Kòz "{cause.name}" {"aktive" if cause.is_active else "deaktive"} avèk siksè!', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Admin toggle_charity_cause failed cause_id={cause_id!r}: {e}")
        flash('Erè pandan modifikasyon kòz charite a.', 'error')
    
    return redirect(url_for('admin.charity_donations'))


@admin_bp.route('/charity/causes/delete', methods=['POST'])
@login_required
@admin_required
def delete_charity_cause():
    """Delete a charitable cause"""
    from app.models.charity import CharityCause
    
    try:
        cause_id = request.form.get('cause_id')
        cause = CharityCause.query.filter_by(cause_id=cause_id).first()
        if not cause:
            flash('Kòz pa jwenn.', 'error')
            return redirect(url_for('admin.charity_donations'))
        
        db.session.delete(cause)
        db.session.commit()
        flash(f'Kòz "{cause.name}" efase avèk siksè!', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Admin delete_charity_cause failed cause_id={cause_id!r}: {e}")
        flash('Erè pandan efase kòz charite a.', 'error')
    
    return redirect(url_for('admin.charity_donations'))


