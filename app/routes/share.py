"""
Share Routes Blueprint
Viral sharing and rewards tracking

Short URLs handled here (all prefixed /s/, see blueprint mount url_prefix):
  /s/<ad_id>   → crawler-friendly page for sharing ads on Facebook / WhatsApp /
                 social media. Instead of a naked 302 redirect (which many
                 crawlers refuse to follow while extracting OpenGraph tags), we
                 render a page WITH the target ad's OpenGraph/Twitter meta tags
                 AND a JS/meta-refresh redirect for human users. This guarantees
                 the PREVIEW shows the AD image, title, price, description —
                 NOT the generic Glory2YahPub banner/logo.
  /s/create    → legacy placeholder.
  /s/b/<batch_id> → click tracking gkach rewards for batch share groups.
"""
import uuid as _uuid
import hmac as _hmac
import hashlib as _hashlib

from flask import (
    Blueprint, redirect, request, url_for, current_app, flash, make_response,
    render_template,
)
from flask_login import current_user
from itsdangerous import BadSignature, URLSafeSerializer
from app.services.gkach_service import GkachService
from app import limiter
from datetime import date


share_bp = Blueprint('share', __name__)


def create_batch_referral_token(batch_id, user_id):
    """Create an unforgeable referral token bound to one batch and user."""
    serializer = URLSafeSerializer(
        current_app.config['SECRET_KEY'],
        salt='g2y-batch-referral-v1',
    )
    return serializer.dumps({'batch_id': str(batch_id), 'user_id': str(user_id)})


def _read_batch_referral_token(token, batch_id):
    if not token:
        return None
    serializer = URLSafeSerializer(
        current_app.config['SECRET_KEY'],
        salt='g2y-batch-referral-v1',
    )
    try:
        payload = serializer.loads(token)
    except BadSignature:
        return None
    if not isinstance(payload, dict) or payload.get('batch_id') != str(batch_id):
        return None
    return payload.get('user_id')


def _sign_device_id(device_id):
    """HMAC-SHA256 sign a device id so users cannot forge a random device."""
    key = str(current_app.config.get('SECRET_KEY', '')).encode('utf-8')
    sig = _hmac.new(key, device_id.encode('utf-8'), _hashlib.sha256).hexdigest()[:16]
    return f"{device_id}.{sig}"


def _verify_device_id(value):
    """Return the raw device id if the signed cookie is valid, else None."""
    try:
        if not value or '.' not in value:
            return None
        device_id, _, _sig = value.rpartition('.')
        if not device_id:
            return None
        expected = _sign_device_id(device_id)
        if not _hmac.compare_digest(str(value), str(expected)):
            return None
        return device_id
    except Exception:
        return None


def _get_or_create_device_id():
    """Return a raw device id, creating one if absent or invalid."""
    raw = request.cookies.get('g2y_device')
    verified = _verify_device_id(raw)
    if verified:
        return verified
    return str(_uuid.uuid4())


def _get_client_ip():
    """Use the peer address, or a proxy-validated address from ProxyFix."""
    return request.remote_addr or ''


@share_bp.route('/create', methods=['GET', 'POST'])
def create():
    """Create new ad/post"""
    from flask import render_template, flash, redirect

    flash('Fonksyon sa ap vini byento!', 'info')
    return redirect(url_for('main.index'))


@share_bp.route('/<short_id>')
@limiter.limit("60 per minute")
def single_ad(short_id):
    """Crawler-friendly short URL for a single ad.

    Behaviour (3 goals):
      1. For FACEBOOK / WHATSAPP / LINKEDIN / DISCORD crawlers (user-agents
         matching known scrapers), return a 200 HTML page that EMBEDS the
         ad's og:title / og:image / og:description / product:price tags.
         These crawlers DO NOT follow 302 redirects when extracting OG tags,
         so returning meta tags on the short URL itself is required.
      2. For HUMAN users (normal browser UAs): redirect WITH NO DELAY via JS
         `location.replace` + <meta http-equiv=refresh> fallback, to the
         canonical `/ad/<short_id>` detail page.
      3. Track share_count on the Ad (first non-crawler visit) — this is a
         soft share attribution; real rewards attribution still goes via
         the `/s/b/<batch_id>` authenticated batch_click route above.
    """
    from app.services.ad_service import AdService
    from app.services.redis_service import RedisService
    from app import redis_client, db

    ad_data = None
    ad_model = None
    try:
        ad_data = AdService.get_ad(short_id)
    except Exception:
        ad_data = None

    # If ad not found, or not approved for public view: 404 then flash+redirect.
    if not ad_data or ad_data.get('admin_status') != 'approved':
        flash('Piblisite sa a pa disponib oubyen li poko apwouve.', 'warning')
        return redirect(url_for('main.index'))

    # --- Crawler detection (case-insensitive substring UA match) ---
    ua = (request.headers.get('User-Agent') or '').lower()
    crawler_tokens = [
        'facebookexternalhit', 'facebot', 'fbexternalhit',  # Facebook / Meta scraper
        'whatsapp',   # WhatsApp link preview scraper
        'twitterbot', 'twitter', 'twittercard', 'x-reddit-bot',
        'linkedinbot', 'linkedin', 'slackbot', 'discordbot',
        'telegrambot', 'applebot', 'googlebot', 'google-structured-data-testing-tool',
        'bingbot', 'yandexbot', 'duckduckbot', 'baiduspider',
        'msnbot', 'ogtag', 'opengraph', 'debug', 'validator',
        'curl', 'wget', 'python-requests', 'python-urllib',
    ]
    is_crawler = any(tok in ua for tok in crawler_tokens)

    # Increment share count softly (max 1 per UA-IP per 24h window for
    # non-crawlers to not inflate from bot traffic).
    try:
        if not is_crawler:
            rs = RedisService(redis_client)
            share_key = f"ad:{short_id}:shares:{_get_client_ip()}:{ua[:32]}"
            if not rs.cache_get(share_key):
                from app.models.ad import Ad as _Ad
                row = _Ad.query.filter_by(ad_id=short_id).with_for_update(read=True).first() \
                    if False else _Ad.query.filter_by(ad_id=short_id).first()
                if row is not None:
                    try:
                        row.share_count = (row.share_count or 0) + 1
                        db.session.commit()
                    except Exception:
                        db.session.rollback()
                rs.cache_set(share_key, '1', timeout=60 * 60 * 24)
    except Exception:
        db.session.rollback()

    # Build canonical absolute target URL (meta-refresh + canonical SEO tag)
    try:
        canonical = url_for('main.view_ad', ad_id=short_id, _external=False)
    except Exception:
        canonical = f'/ad/{short_id}'

    # Render the crawler-friendly short-page (contains full OG + redirect code)
    resp_body = render_template(
        'share_shortlink.html',
        ad=ad_data,
        canonical_path=canonical,
        is_crawler=is_crawler,
    )

    response = make_response(resp_body)
    # Crawlers like Facebook ignore no-cache headers, but humans need a fresh
    # redirect if the ad changes status later.
    response.headers['Cache-Control'] = 'max-age=60, public, immutable' if is_crawler else 'no-cache, no-store, must-revalidate'
    response.headers['Vary'] = 'User-Agent'
    return response


@share_bp.route('/b/<batch_id>')
@limiter.limit("6 per minute")
def batch_click(batch_id):
    """Track a signed referral and display the approved ads in its batch."""
    from app.models.batch import Batch
    from app.models.batch_ad import BatchAd
    from app.models.ad import Ad
    from app.models.user import User
    from app import db

    referrer_id = _read_batch_referral_token(request.args.get('ref'), batch_id)
    if referrer_id is None:
        flash('Lyen pataj sa a pa valab.', 'warning')
        return redirect(url_for('main.index'))

    try:
        referrer_user = db.session.get(User, int(referrer_id))
    except (TypeError, ValueError):
        referrer_user = None
    if not referrer_user or not referrer_user.is_active or not referrer_user.whatsapp:
        flash('Kont moun ki pataje lyen sa a pa disponib.', 'warning')
        return redirect(url_for('main.index'))

    batch = Batch.query.filter_by(batch_id=batch_id).first()
    if not batch:
        flash('Gwoup piblisite sa pa jwenn.', 'error')
        return redirect(url_for('main.index'))

    ads = (
        Ad.query.join(BatchAd, BatchAd.ad_id == Ad.ad_id)
        .filter(
            BatchAd.batch_id == batch_id,
            Ad.admin_status == 'approved',
            Ad.deleted_at.is_(None),
        )
        .order_by(BatchAd.position.asc(), BatchAd.id.asc())
        .all()
    )
    if not ads:
        flash('Gwoup sa a pa gen piblisite apwouve pou montre.', 'warning')
        return redirect(url_for('main.index'))

    device_id = None
    if current_user.is_authenticated and current_user.whatsapp:
        try:
            device_id = _get_or_create_device_id()
            tracked = GkachService.track_batch_click(
                batch_id,
                referrer_user.whatsapp,
                clicker_whatsapp=current_user.whatsapp,
                dedup_key=f'{current_user.whatsapp}|{batch_id}|{date.today().isoformat()}',
                clicker_ip=_get_client_ip(),
                clicker_device=device_id,
            )
            if not tracked:
                flash('Klik sa a pa konte oswa li te deja anrejistre.', 'info')
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Error tracking signed batch referral')
            flash('Nou pa kapab anrejistre klik la kounye a.', 'error')
    elif current_user.is_authenticated:
        flash('Nimewo WhatsApp pa disponib pou konte klik sa a.', 'warning')

    response = make_response(render_template(
        'batch.html',
        batch=batch,
        ads=ads,
        login_for_rewards_url=(
            url_for('auth.login', next=request.full_path)
            if not current_user.is_authenticated else None
        ),
    ))
    if device_id:
        response.set_cookie(
            'g2y_device',
            _sign_device_id(device_id),
            max_age=60 * 60 * 24 * 365,
            httponly=True,
            samesite='Lax',
            secure=request.is_secure,
        )
    return response
