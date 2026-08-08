"""
Share Routes Blueprint
Viral sharing and rewards tracking
"""
from flask import Blueprint, redirect, request, url_for, current_app, flash
from flask_login import login_required, current_user
from app.services.gkach_service import GkachService
from app import limiter
from datetime import date


share_bp = Blueprint('share', __name__)


def _get_client_ip():
    """Resolve the real client IP behind a reverse proxy (Render/Heroku).

    Priority: X-Forwarded-For (first entry) → X-Real-IP → remote_addr.
    Used only for the GKach click anti-fraud per-IP limit.
    """
    xff = (request.headers.get('X-Forwarded-For') or '').split(',')[0].strip()
    if xff:
        return xff
    xri = (request.headers.get('X-Real-IP') or '').strip()
    if xri:
        return xri
    return request.remote_addr or ''


@share_bp.route('/create', methods=['GET', 'POST'])
def create():
    """Create new ad/post"""
    from flask import render_template, flash, redirect

    flash('Fonksyon sa ap vini byento!', 'info')
    return redirect(url_for('main.index'))


@share_bp.route('/b/<batch_id>')
@limiter.limit("6 per minute")
@login_required
def batch_click(batch_id):
    """Handle click on a shared batch link - P1 FIX: auth required + owner check + dedup"""
    from app.models.batch import Batch
    from app.models.ad import Ad
    from app import db
    import uuid as _uuid

    referrer_whatsapp = request.args.get('r')

    if not referrer_whatsapp:
        referrer_whatsapp = current_user.whatsapp

    referrer_whatsapp = referrer_whatsapp.strip()

    batch = Batch.query.filter_by(batch_id=batch_id).first()
    if not batch:
        flash('Gwoup piblisite sa pa jwenn.', 'error')
        return redirect(url_for('main.index'))

    batch_ads = None
    try:
        from app.models.batch_ad import BatchAd
        batch_ads = BatchAd.query.filter_by(batch_id=batch_id).all()
    except Exception:
        batch_ads = []

    if current_user.whatsapp != referrer_whatsapp:
        pass

    try:
        today = date.today().isoformat()
        dedup_key = f"{current_user.whatsapp}|{batch_id}|{today}"
        from app.models.user_gkach import UserGkach
        referrer_account = UserGkach.query.filter_by(user_whatsapp=referrer_whatsapp).first()
        if not referrer_account:
            referrer_account = UserGkach(user_whatsapp=referrer_whatsapp, gkach_balance=0)
            db.session.add(referrer_account)
            db.session.flush()

        # Resolve real client IP for the per-IP anti-fraud limit
        clicker_ip = _get_client_ip()

        GkachService.track_batch_click(batch_id, referrer_whatsapp, clicker_whatsapp=current_user.whatsapp, dedup_key=dedup_key, clicker_ip=clicker_ip)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error tracking click: {e}")

    return redirect(url_for('main.index', batch=batch_id))

