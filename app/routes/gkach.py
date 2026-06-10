"""
Gkach Routes Blueprint
Virtual currency management and requests
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.services.gkach_service import GkachService
from app.utils.validators import ValidationError


gkach_bp = Blueprint('gkach', __name__)


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
    if request.method == 'POST':
        try:
            amount = int(request.form.get('amount', 0))
            if amount <= 0:
                raise ValidationError("Kantite dwe pi gran pase 0")
                
            # Logic for Gkach request (will be stored in JSON field for now)
            # In Phase 5 we will implement a more robust reward/purchase system
            flash('Demann ou an voye bay administratè a!', 'success')
            return redirect(url_for('gkach.wallet'))
        except ValidationError as e:
            flash(str(e), 'error')
        except Exception as e:
            flash('Erè nan demann Gkach.', 'error')
            
    return render_template('gkach/request.html')


@gkach_bp.route('/transfer', methods=['GET', 'POST'])
@login_required
def transfer():
    """Transfer Gkach to another user"""
    if request.method == 'POST':
        try:
            to_whatsapp = request.form.get('whatsapp', '').strip()
            amount = int(request.form.get('amount', 0))
            description = request.form.get('description', '').strip()
            
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
            
    return render_template('gkach/transfer.html')


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
