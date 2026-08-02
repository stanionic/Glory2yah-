"""
Bank Models - Loans and Investments
"""
from app import db
from app.models.base import BaseModel
from datetime import datetime, timedelta
import uuid


class LoanProduct(BaseModel):
    """Loan product model"""
    __tablename__ = 'loan_products'

    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    min_amount = db.Column(db.Integer, default=100)
    max_amount = db.Column(db.Integer, default=10000)
    interest_rate = db.Column(db.Float, default=5.0)  # % per year
    duration_days = db.Column(db.Integer, default=30)
    is_active = db.Column(db.Boolean, default=True)

    # Relationships
    loans = db.relationship('Loan', backref='product', lazy=True)

    def __repr__(self):
        return f'<LoanProduct {self.name}>'


class Loan(db.Model):
    """Loan model"""
    __tablename__ = 'loans'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    loan_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    product_id = db.Column(db.Integer, db.ForeignKey('loan_products.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    interest_amount = db.Column(db.Integer, default=0)
    total_due = db.Column(db.Integer, nullable=False)
    purpose = db.Column(db.Text)
    status = db.Column(db.String(20), default='pending')  # pending, active, completed, rejected, defaulted
    due_date = db.Column(db.DateTime)
    approved_at = db.Column(db.DateTime)
    repaid_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    user = db.relationship('User', backref='loans')
    repayments = db.relationship('LoanRepayment', backref='loan', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Loan {self.loan_id[:8]} - {self.amount} Gkach>'


class LoanRepayment(db.Model):
    """Loan repayment model"""
    __tablename__ = 'loan_repayments'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    repayment_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    loan_id = db.Column(db.String(36), db.ForeignKey('loans.loan_id'), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<LoanRepayment {self.repayment_id[:8]} - {self.amount} Gkach>'


class InvestmentProduct(BaseModel):
    """Investment product model"""
    __tablename__ = 'investment_products'

    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    min_amount = db.Column(db.Integer, default=100)
    max_amount = db.Column(db.Integer, nullable=True)
    interest_rate = db.Column(db.Float, default=8.0)  # % per year
    duration_days = db.Column(db.Integer, default=90)
    early_withdrawal_penalty = db.Column(db.Float, default=10.0)  # %
    is_active = db.Column(db.Boolean, default=True)

    # Relationships
    investments = db.relationship('Investment', backref='product', lazy=True)

    def __repr__(self):
        return f'<InvestmentProduct {self.name}>'


class Investment(db.Model):
    """Investment model"""
    __tablename__ = 'investments'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    investment_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    product_id = db.Column(db.Integer, db.ForeignKey('investment_products.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    expected_return = db.Column(db.Integer, nullable=False)
    auto_renew = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default='active')  # active, completed, withdrawn_early
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    matures_at = db.Column(db.DateTime, nullable=False)
    withdrawn_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    user = db.relationship('User', backref='investments')

    def __repr__(self):
        return f'<Investment {self.investment_id[:8]} - {self.amount} Gkach>'