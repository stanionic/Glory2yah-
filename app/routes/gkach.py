"""
Gkach Routes Blueprint
Virtual currency management and requests
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from app import limiter
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
    """Reward dashboard with approved signed-share links and click progress."""
    from app import db
    from app.models.batch import Batch
    from app.models.batch_ad import BatchAd
    from app.models.batch_click import BatchClick
    from app.models.ad import Ad
    from sqlalchemy import func as _sa_fn
    from app.routes.share import create_batch_referral_token
    from app.utils.site_url import absolute_url

    whatsapp = current_user.whatsapp
    click_counts = dict(
        db.session.query(BatchClick.batch_id, _sa_fn.count(BatchClick.id))
        .filter_by(referrer_whatsapp=whatsapp)
        .group_by(BatchClick.batch_id)
        .all()
    )
    total_clicks = sum(click_counts.values())

    approved_batch_ids = (
        db.session.query(BatchAd.batch_id)
        .join(Ad, Ad.ad_id == BatchAd.ad_id)
        .filter(Ad.admin_status == 'approved', Ad.deleted_at.is_(None))
        .distinct()
    )
    required_clicks = max(1, int(current_app.config.get('GKACH_CLICKS_REQUIRED', 100) or 100))
    reward_amount = max(1, int(current_app.config.get('GKACH_REWARD_AMOUNT', 10) or 10))
    share_batches = []
    batches = (
        Batch.query.filter(Batch.batch_id.in_(approved_batch_ids))
        .order_by(Batch.created_at.desc())
        .limit(25)
        .all()
    )
    for batch in batches:
        token = create_batch_referral_token(batch.batch_id, current_user.id)
        path = url_for('share.batch_click', batch_id=batch.batch_id, ref=token)
        clicks = click_counts.get(batch.batch_id, 0)
        share_batches.append({
            'batch': batch,
            'clicks': clicks,
            'progress': clicks % required_clicks,
            'remaining': required_clicks - (clicks % required_clicks),
            'earned': (clicks // required_clicks) * reward_amount,
            'share_url': absolute_url(path),
        })

    gkach_balance = GkachService.get_balance(whatsapp)
    recent_txns = GkachService.get_transactions(whatsapp, limit=20)
    # get_transactions() returns dicts whose 'created_at' is an ISO *string*
    # (see GkachTransaction.to_dict). The template used to call .strftime() on
    # it, which raised UndefinedError ('str' has no 'strftime') and 500'd the
    # page for ANY user with transactions. Pre-format into 'created_at_str' so
    # the template renders a plain string regardless of the source type.
    from datetime import datetime as _dt
    for _t in recent_txns:
        if not isinstance(_t, dict):
            continue
        _ca = _t.get('created_at')
        _fmt = ''
        if isinstance(_ca, str) and _ca:
            try:
                _fmt = _dt.fromisoformat(_ca).strftime('%d/%m/%Y %H:%M')
            except (ValueError, TypeError):
                _fmt = _ca
        elif _ca is not None:
            try:
                _fmt = _ca.strftime('%d/%m/%Y %H:%M')
            except (ValueError, TypeError, AttributeError):
                _fmt = str(_ca)
        _t['created_at_str'] = _fmt
    s = GkachService.get_transaction_summary(whatsapp)
    total_sales = int((s.get('sale') or {}).get('total') or 0)

    return render_template(
        'reward_dashboard.html',
        total_clicks=total_clicks,
        total_sales=total_sales,
        gkach_balance=gkach_balance,
        share_batches=share_batches,
        required_clicks=required_clicks,
        reward_amount=reward_amount,
        recent_txns=recent_txns,
    )


@gkach_bp.route('/request', methods=['GET', 'POST'])
@login_required
@limiter.limit('5 per hour', methods=['POST'])
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
                    from app.services.gkach_proof_service import save_gkach_proof
                    document_filename = save_gkach_proof(file, max_size_mb=10)
            
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

            # ── ADMIN APPROVAL TRAFFIC ───────────────────────────────────────
            # Recharge requests stay 'pending' until an admin credits the wallet.
            try:
                from app.services.admin_approval_alerts import alert_recharge_request
                alert_recharge_request(
                    current_user.whatsapp, amount,
                    request_id=new_request.get('request_id'),
                    currency=currency, payment_method=payment_method,
                )
            except Exception as _alert_err:
                current_app.logger.warning('recharge approval alert failed: %s', _alert_err)

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


@gkach_bp.route('/withdraw', methods=['GET', 'POST'])
@login_required
def withdraw():
    """Request cash withdrawal (Gkach -> fiat). Min = GKACH_WITHDRAW_MIN (500 Gk default)."""
    from app.utils.validators import validate_amount, sanitize_text, ValidationError
    from flask import current_app as _ca

    whatsapp = current_user.whatsapp
    balance = GkachService.get_balance(whatsapp)
    min_withdraw = int(_ca.config.get('GKACH_WITHDRAW_MIN', 500) or 500)
    rate = float(_ca.config.get('GKACH_TO_HTG_RATE', 1.2) or 1.2)

    pending = GkachService.get_transactions(whatsapp, limit=20)
    pending_withdrawals = [
        t for t in pending
        if t.get('transaction_type') == 'withdrawal' and t.get('status') == 'pending'
    ]

    if request.method == 'POST':
        try:
            amount = validate_amount(request.form.get('amount'), min_amount=min_withdraw)
            payment_method = sanitize_text(request.form.get('payment_method', 'moncash')) or 'moncash'
            payout_details = sanitize_text(request.form.get('payout_details', ''))
            note = sanitize_text(request.form.get('note', ''))

            tx_id = GkachService.request_withdrawal(
                whatsapp, amount,
                payment_method=payment_method,
                payout_details=payout_details,
                note=note,
            )
            # ── ADMIN APPROVAL TRAFFIC ───────────────────────────────────────
            # The balance is only debited when an admin approves the request.
            try:
                from app.services.admin_approval_alerts import alert_withdrawal_request
                alert_withdrawal_request(
                    whatsapp, amount, transaction_id=tx_id,
                    payment_method=payment_method, payout_details=payout_details,
                )
            except Exception as _alert_err:
                current_app.logger.warning('withdrawal approval alert failed: %s', _alert_err)
            flash(
                f'Demann retriz {amount} Gkach voye! Admin ap revize l byento.'
                f' (≈ {round(amount * rate, 2):.2f} HTG)',
                'success'
            )
            return redirect(url_for('gkach.wallet'))
        except ValidationError as e:
            flash(str(e), 'error')
        except Exception as e:
            flash(f'Erè nan demann retriz: {str(e)}', 'error')

    return render_template(
        'gkach/withdraw.html',
        balance=balance,
        min_withdraw=min_withdraw,
        rate=rate,
        pending_withdrawals=pending_withdrawals,
    )


@gkach_bp.route('/api/summary')
@login_required
def api_summary():
    """Return earnings and unique clicks attributed to this user's batch links."""
    from app import db
    from app.models.batch_click import BatchClick
    from sqlalchemy import func as _sa_fn2
    try:
        summary = GkachService.get_transaction_summary(current_user.whatsapp)
        total_clicks = int(
            db.session.query(_sa_fn2.count(BatchClick.id))
            .filter_by(referrer_whatsapp=current_user.whatsapp)
            .scalar() or 0
        )
        return jsonify({
            'success': True,
            'total_clicks': total_clicks,
            'reward_earnings': summary.get('reward', {}).get('total', 0),
            'sales_earnings': summary.get('sale', {}).get('total', 0),
            'cashback_earnings': summary.get('cashback', {}).get('total', 0),
            'referral_earnings': summary.get('transfer_in', {}).get('total', 0)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
