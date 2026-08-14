"""
Gkach Routes Blueprint
Virtual currency management and requests
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from app.services.gkach_service import GkachService, UserGkach
from app.utils.validators import ValidationError


gkach_bp = Blueprint('gkach', __name__)


@gkach_bp.route('/')
def index():
    """Redirect to wallet"""
    return redirect(url_for('gkach.wallet'))


@gkach_bp.route('/wallet')
@login_required
def wallet():
    """View wallet balance and history"""
    balance = GkachService.get_balance(current_user.whatsapp)
    transactions = GkachService.get_transactions(current_user.whatsapp)
    
    return render_template(
        'gkach/wallet.html',
        balance=balance,
        transactions=transactions,
        current_user=current_user
    )


@gkach_bp.route('/rewards/dashboard')
@login_required
def rewards_dashboard():
    """Tableau de bord rekonpans itilizatè: klik pataje yo, vant, balans Gkach,
    pwogre pou chak 100 klik pou rekonpans prochain."""
    from app import db
    from app.models.ad import Ad
    from sqlalchemy import func as _sa_fn

    whatsapp = current_user.whatsapp

    _bc_clicks = 0
    try:
        from app.models.batch_click import BatchClick
        _bc_clicks = int(
            db.session.query(_sa_fn.count(BatchClick.id))
            .filter(BatchClick.referrer == whatsapp)
            .scalar() or 0
        )
    except Exception:
        _bc_clicks = 0

    _own_clicks = 0
    try:
        q = db.session.query(_sa_fn.coalesce(_sa_fn.sum(Ad.share_count), 0)).filter(Ad.user_whatsapp == whatsapp)
        if hasattr(Ad, 'deleted_at'):
            q = q.filter(Ad.deleted_at.is_(None))
        _own_clicks = int(q.scalar() or 0)
    except Exception:
        _own_clicks = 0

    total_clicks = _bc_clicks + _own_clicks

    trackings = []
    try:
        q_ads = Ad.query.filter_by(user_whatsapp=whatsapp)
        if hasattr(Ad, 'created_at'):
            q_ads = q_ads.order_by(Ad.created_at.desc())
        elif hasattr(Ad, 'ad_id'):
            q_ads = q_ads.order_by(Ad.ad_id.desc())
        for a in q_ads.limit(25).all():
            trackings.append({'ad': a, 'clicks': int(a.share_count or 0), 'sales': 0,
                              'title': a.title, 'ad_id': a.ad_id})
    except Exception:
        trackings = []

    gkach_balance = GkachService.get_balance(whatsapp)
    recent_txns = GkachService.get_transactions(whatsapp, limit=20)
    total_sales = 0
    try:
        s = GkachService.get_transaction_summary(whatsapp)
        if isinstance(s, dict):
            total_sales = int((s.get('sale') or {}).get('total') or 0)
    except Exception:
        total_sales = 0

    return render_template(
        'reward_dashboard.html',
        total_clicks=total_clicks,
        total_sales=total_sales,
        gkach_balance=gkach_balance,
        trackings=trackings,
        recent_txns=recent_txns,
    )


@gkach_bp.route('/request', methods=['GET', 'POST'])
@login_required
def request_gkach():
    """Request Gkach (recharge)"""    
    from app.utils.validators import validate_amount, ValidationError
    from app import db
    from datetime import datetime
    import uuid
    import os

    account = GkachService.get_or_create_account(current_user.whatsapp)

    if request.method == 'POST':
        try:
            amount = validate_amount(request.form.get('amount'), min_amount=1)
            currency = request.form.get('currency', 'HTG')
            payment_method = request.form.get('payment_method', 'moncash')
            
            document_filename = None
            if 'document' in request.files:
                file = request.files['document']
                if file and file.filename:
                    # Save file
                    ext = file.filename.rsplit('.', 1)[1].lower()
                    document_filename = f"gkach_req_{uuid.uuid4().hex}.{ext}"
                    file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], document_filename))
            
            # Save request
            if not account.gkach_requests or account.gkach_requests == '[]':
                requests_list = []
            else:
                import json
                requests_list = json.loads(account.gkach_requests)
            
            new_request = {
                'request_id': str(uuid.uuid4()),
                'amount': amount,
                'currency': currency,
                'payment_method': payment_method,
                'document': document_filename,
                'status': 'pending',
                'requested_at': datetime.now().strftime('%d/%m/%Y %H:%M')
            }
            requests_list.append(new_request)
            
            import json
            account.gkach_requests = json.dumps(requests_list)
            db.session.commit()
            
            flash('Demann ou an voye bay administratè a!', 'success')
            return redirect(url_for('gkach.wallet'))
        except ValidationError as e:
            flash(str(e), 'error')
        except Exception as e:
            db.session.rollback()
            flash('Erè nan demann Gkach.', 'error')
            
    return render_template('gkach/request.html', account=account)


@gkach_bp.route('/transfer', methods=['GET', 'POST'])
@login_required
def transfer():
    """Transfer Gkach to another user"""    
    from app.utils.validators import validate_whatsapp, validate_amount, sanitize_text, ValidationError

    balance = GkachService.get_balance(current_user.whatsapp)
    transactions = GkachService.get_transactions(current_user.whatsapp, limit=20)

    if request.method == 'POST':
        try:
            to_whatsapp = validate_whatsapp(request.form.get('recipient'))
            amount = validate_amount(request.form.get('amount'), min_amount=1)
            description = sanitize_text(request.form.get('note', ''))
            GkachService.transfer(
                current_user.whatsapp,
                to_whatsapp,
                amount,
                description
            )
            
            flash(f'Ou transfere {amount} Gkach bay {to_whatsapp} avèk siksè!', 'success')
            return redirect(url_for('gkach.wallet'))
        except ValidationError as e:
            flash(str(e), 'error')
        except Exception as e:
            flash('Erè nan transfè Gkach.', 'error')
            
    return render_template('gkach/transfer.html', balance=balance, transactions=transactions)


@gkach_bp.route('/api/summary')
@login_required
def api_summary():
    """API endpoint for earnings summary.
    `total_clicks` is computed LIVE from BatchClick unique referrals +
    Ad.share_count for the user's own ads (replaces the old zero TODO)."""
    from app import db
    from app.models.ad import Ad
    from sqlalchemy import func as _sa_fn2
    try:
        summary = GkachService.get_transaction_summary(current_user.whatsapp)
        whatsapp = current_user.whatsapp
        tc = 0
        try:
            from app.models.batch_click import BatchClick
            tc += int(
                db.session.query(_sa_fn2.count(BatchClick.id))
                .filter(BatchClick.referrer == whatsapp)
                .scalar() or 0
            )
        except Exception:
            pass
        try:
            q2 = db.session.query(_sa_fn2.coalesce(_sa_fn2.sum(Ad.share_count), 0)).filter(Ad.user_whatsapp == whatsapp)
            if hasattr(Ad, 'deleted_at'):
                q2 = q2.filter(Ad.deleted_at.is_(None))
            tc += int(q2.scalar() or 0)
        except Exception:
            pass
        return jsonify({
            'success': True,
            'total_clicks': int(tc or 0),
            'reward_earnings': summary.get('reward', {}).get('total', 0),
            'sales_earnings': summary.get('sale', {}).get('total', 0),
            'referral_earnings': summary.get('transfer_in', {}).get('total', 0)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
