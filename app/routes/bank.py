"""
Bank Blueprint - Loans and Investments
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from app import db
from app.models.bank import LoanProduct, Loan, LoanRepayment, InvestmentProduct, Investment
from app.models.user_gkach import UserGkach
from app.services.gkach_service import GkachService
from app.utils.validators import ValidationError
from datetime import datetime, timedelta
import uuid

bank_bp = Blueprint('bank', __name__, url_prefix='/bank')


@bank_bp.route('/')
@login_required
def dashboard():
    """Bank dashboard"""
    # Get user's Gkach balance
    gkach_balance = GkachService.get_balance(current_user.whatsapp)

    # Get active loans
    active_loans = Loan.query.filter_by(
        user_id=current_user.id,
        status='active'
    ).all()

    # Get active investments
    active_investments = Investment.query.filter_by(
        user_id=current_user.id,
        status='active'
    ).all()

    # Calculate total loan due
    total_loan_due = sum(loan.total_due for loan in active_loans)

    # Calculate total invested
    total_invested = sum(inv.amount for inv in active_investments)

    return render_template(
        'bank_dashboard.html',
        gkach_balance=gkach_balance,
        active_loans=active_loans,
        active_investments=active_investments,
        total_loan_due=total_loan_due,
        total_invested=total_invested
    )


@bank_bp.route('/loans')
@login_required
def loan_list():
    """List loan products and user's loans"""
    loan_products = LoanProduct.query.filter_by(is_active=True).all()
    user_loans = Loan.query.filter_by(user_id=current_user.id).order_by(Loan.created_at.desc()).all()
    return render_template('loan_list.html', loan_products=loan_products, user_loans=user_loans)


@bank_bp.route('/loans/apply/<int:product_id>', methods=['GET', 'POST'])
@login_required
def loan_apply(product_id):
    """Apply for a loan"""
    product = LoanProduct.query.get_or_404(product_id)

    if request.method == 'POST':
        amount = int(request.form.get('amount', 0))
        purpose = request.form.get('purpose', '')

        if amount < product.min_amount or amount > product.max_amount:
            flash(f'Kantite dwe ant {product.min_amount} ak {product.max_amount} Gkach', 'error')
            return redirect(url_for('bank.loan_apply', product_id=product_id))

        # Calculate interest
        interest_amount = int(amount * product.interest_rate / 100 * product.duration_days / 365)
        total_due = amount + interest_amount
        due_date = datetime.utcnow() + timedelta(days=product.duration_days)

        loan = Loan(
            loan_id=str(uuid.uuid4()),
            product_id=product.id,
            user_id=current_user.id,
            amount=amount,
            interest_amount=interest_amount,
            total_due=total_due,
            purpose=purpose,
            status='pending',
            due_date=due_date
        )
        db.session.add(loan)
        db.session.commit()

        flash('Demann prè ou anrejistre! Admin ap revize li.', 'success')
        return redirect(url_for('bank.loan_list'))

    return render_template('loan_apply.html', product=product)


@bank_bp.route('/loans/repay/<loan_id>', methods=['POST'])
@login_required
def loan_repay(loan_id):
    """Repay a loan"""
    loan = Loan.query.filter_by(loan_id=loan_id, user_id=current_user.id).first_or_404()

    if loan.status != 'active':
        flash('Prè sa a pa aktif', 'error')
        return redirect(url_for('bank.dashboard'))

    amount = int(request.form.get('amount', 0))
    if amount <= 0:
        flash('Kantite dwe pozitif', 'error')
        return redirect(url_for('bank.dashboard'))

    # Check total paid so far
    total_paid = sum(r.amount for r in loan.repayments)
    remaining = loan.total_due - total_paid

    if amount > remaining:
        amount = remaining

    try:
        # Deduct from user's Gkach balance
        GkachService.deduct_balance(
            current_user.whatsapp,
            amount,
            f"Rembousman prè {loan.loan_id[:8]}",
            'loan_repayment'
        )

        # Record repayment
        repayment = LoanRepayment(
            repayment_id=str(uuid.uuid4()),
            loan_id=loan.loan_id,
            amount=amount
        )
        db.session.add(repayment)

        # Check if loan is fully repaid
        new_total_paid = total_paid + amount
        if new_total_paid >= loan.total_due:
            loan.status = 'completed'
            loan.repaid_at = datetime.utcnow()

        db.session.commit()
        flash(f'Peyman {amount} Gkach reyisi!', 'success')
    except ValidationError as e:
        flash(str(e), 'error')
    except Exception as e:
        db.session.rollback()
        flash(f'Erè nan peyman: {str(e)}', 'error')

    return redirect(url_for('bank.dashboard'))


@bank_bp.route('/investments')
@login_required
def investment_products():
    """List investment products"""
    products = InvestmentProduct.query.filter_by(is_active=True).all()
    return render_template('investment_products.html', products=products)


@bank_bp.route('/investments/my')
@login_required
def my_investments():
    """List user's investments"""
    investments = Investment.query.filter_by(user_id=current_user.id).order_by(Investment.started_at.desc()).all()
    return render_template('my_investments.html', investments=investments)


@bank_bp.route('/investments/invest/<int:product_id>', methods=['POST'])
@login_required
def invest(product_id):
    """Make an investment"""
    product = InvestmentProduct.query.get_or_404(product_id)
    amount = int(request.form.get('amount', 0))
    auto_renew = request.form.get('auto_renew') == 'on'

    if amount < product.min_amount:
        flash(f'Kantite minimòm se {product.min_amount} Gkach', 'error')
        return redirect(url_for('bank.investment_products'))

    if product.max_amount and amount > product.max_amount:
        flash(f'Kantite maksimòm se {product.max_amount} Gkach', 'error')
        return redirect(url_for('bank.investment_products'))

    # Calculate expected return
    expected_return = int(amount * product.interest_rate / 100 * product.duration_days / 365)
    matures_at = datetime.utcnow() + timedelta(days=product.duration_days)

    try:
        # Deduct from user's Gkach balance
        GkachService.deduct_balance(
            current_user.whatsapp,
            amount,
            f"Envestisman: {product.name}",
            'investment'
        )

        # Create investment
        investment = Investment(
            investment_id=str(uuid.uuid4()),
            product_id=product.id,
            user_id=current_user.id,
            amount=amount,
            expected_return=expected_return,
            auto_renew=auto_renew,
            status='active',
            matures_at=matures_at
        )
        db.session.add(investment)
        db.session.commit()

        flash(f'Envestisman {amount} Gkach reyisi! Retou atann: {expected_return} Gkach', 'success')
    except ValidationError as e:
        flash(str(e), 'error')
    except Exception as e:
        db.session.rollback()
        flash(f'Erè nan envestisman: {str(e)}', 'error')

    return redirect(url_for('bank.my_investments'))


@bank_bp.route('/investments/withdraw/<investment_id>', methods=['POST'])
@login_required
def withdraw_investment(investment_id):
    """Withdraw an investment early"""
    investment = Investment.query.filter_by(investment_id=investment_id, user_id=current_user.id).first_or_404()

    if investment.status != 'active':
        flash('Envestisman sa a pa aktif', 'error')
        return redirect(url_for('bank.my_investments'))

    # Calculate penalty
    penalty = int(investment.amount * investment.product.early_withdrawal_penalty / 100)
    return_amount = investment.amount - penalty

    try:
        # Add back to user's Gkach balance
        GkachService.add_balance(
            current_user.whatsapp,
            return_amount,
            f"Retrè envestisman {investment.investment_id[:8]} (penalite {penalty} Gkach)",
            'investment_withdrawal'
        )

        investment.status = 'withdrawn_early'
        investment.withdrawn_at = datetime.utcnow()
        db.session.commit()

        flash(f'Retrè reyisi! Ou resevwa {return_amount} Gkach (penalite {penalty} Gkach)', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erè nan retrè: {str(e)}', 'error')

    return redirect(url_for('bank.my_investments'))


# ==================== ADMIN ROUTES ====================

@bank_bp.route('/admin')
@login_required
def admin_bank():
    """Admin bank dashboard"""
    if not current_user.is_admin:
        flash('Aksè refize', 'error')
        return redirect(url_for('main.index'))

    pending_loans = Loan.query.filter_by(status='pending').count()
    active_loans = Loan.query.filter_by(status='active').count()
    total_investments = Investment.query.filter_by(status='active').count()
    recent_loans = Loan.query.order_by(Loan.created_at.desc()).limit(10).all()

    return render_template(
        'admin_bank.html',
        pending_loans=pending_loans,
        active_loans=active_loans,
        total_investments=total_investments,
        recent_loans=recent_loans
    )


@bank_bp.route('/admin/loans/approve/<loan_id>', methods=['POST'])
@login_required
def admin_approve_loan(loan_id):
    """Approve a loan"""
    if not current_user.is_admin:
        flash('Aksè refize', 'error')
        return redirect(url_for('main.index'))

    loan = Loan.query.filter_by(loan_id=loan_id).first_or_404()
    loan.status = 'active'
    loan.approved_at = datetime.utcnow()
    db.session.commit()

    # Add loan amount to user's Gkach balance
    try:
        GkachService.add_balance(
            loan.user.whatsapp,
            loan.amount,
            f"Prè apwouve: {loan.loan_id[:8]}",
            'loan_disbursement'
        )
    except Exception as e:
        current_app.logger.error(f"Error disbursing loan: {e}")

    flash(f'Prè {loan.loan_id[:8]} apwouve!', 'success')
    return redirect(url_for('bank.admin_bank'))


@bank_bp.route('/admin/loans/reject/<loan_id>', methods=['POST'])
@login_required
def admin_reject_loan(loan_id):
    """Reject a loan"""
    if not current_user.is_admin:
        flash('Aksè refize', 'error')
        return redirect(url_for('main.index'))

    loan = Loan.query.filter_by(loan_id=loan_id).first_or_404()
    loan.status = 'rejected'
    db.session.commit()

    flash(f'Prè {loan.loan_id[:8]} rejte', 'success')
    return redirect(url_for('bank.admin_bank'))