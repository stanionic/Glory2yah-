"""
Gkach Routes Blueprint
Virtual currency management and requests
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
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
                    file.save(os.path.join('static/uploads', document_filename))
            
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
    """API endpoint for earnings summary"""
    try:
        summary = GkachService.get_transaction_summary(current_user.whatsapp)
        
        return jsonify({
            'success': True,
            'total_clicks': 0,  # TODO: Implement click tracking
            'reward_earnings': summary.get('reward', {}).get('total', 0),
            'sales_earnings': summary.get('sale', {}).get('total', 0),
            'referral_earnings': summary.get('transfer_in', {}).get('total', 0)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
