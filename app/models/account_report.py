from app import db
from app.models.base import BaseModel


class AccountReport(BaseModel):
    """A user-submitted report about another account."""

    __tablename__ = 'account_reports'
    __table_args__ = (
        db.UniqueConstraint('reporter_id', 'reported_user_id',
                            name='uq_account_reporter_target'),
    )

    reporter_id = db.Column(db.Integer, db.ForeignKey('users.id'),
                            nullable=False, index=True)
    reported_user_id = db.Column(db.Integer, db.ForeignKey('users.id'),
                                 nullable=False, index=True)
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='open', index=True)
