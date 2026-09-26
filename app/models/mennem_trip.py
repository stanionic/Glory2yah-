"""
Mennen M Trip Model
Trip request + price negotiation flow (mirrors MACHE checkout negotiation):
  negotiating -> accepted -> paid/demo -> completed
  cancelled at any time before payment.
"""
from datetime import datetime
import json

from app import db
from app.models.base import BaseModel


class MennemTrip(BaseModel):
    """Mennen M Trip Model."""

    __tablename__ = 'mennem_trips'

    # Trip details
    from_location = db.Column(db.String(255), nullable=False)
    to_location = db.Column(db.String(255), nullable=False)
    price_gkach = db.Column(db.Integer, nullable=False, default=0)  # agreed/accepted price

    # Driver details (snapshot + live FK)
    driver_id = db.Column(db.Integer, db.ForeignKey('mennem_drivers.id'), nullable=True, index=True)
    driver_name = db.Column(db.String(255), nullable=False)
    driver_phone = db.Column(db.String(50), nullable=False)
    driver_rating = db.Column(db.Float, default=0.0)

    # Passenger details
    passenger_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    passenger_whatsapp = db.Column(db.String(50), nullable=False)

    # Price negotiation (MACHE checkout style)
    proposed_price = db.Column(db.Integer, nullable=True)   # latest client proposal
    counter_price = db.Column(db.Integer, nullable=True)    # latest driver counter-offer
    accepted_price = db.Column(db.Integer, nullable=True)   # price both parties agreed on
    negotiation_history = db.Column(db.Text, nullable=True) # JSON array of events

    # Trip status: negotiating, accepted, paid, demo, completed, cancelled
    status = db.Column(db.String(50), default='negotiating', nullable=False, index=True)

    # Relationships
    passenger = db.relationship('User', backref='mennem_trips')
    driver = db.relationship('MennemDriver', backref='mennem_trips')

    # ------------------------------------------------------------------
    # Negotiation helpers
    # ------------------------------------------------------------------
    def history(self):
        """Return the negotiation history as a Python list."""
        if not self.negotiation_history:
            return []
        try:
            data = json.loads(self.negotiation_history)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def add_history_event(self, role, message, price=None, rating=None):
        """Append an event to the negotiation history (in-memory, caller commits)."""
        events = self.history()
        events.append({
            'at': datetime.utcnow().isoformat(),
            'role': role,             # 'client' | 'driver' | 'system'
            'message': message,
            'price': price,
            'rating': rating,
        })
        self.negotiation_history = json.dumps(events, ensure_ascii=False)

    def client_rating(self):
        """Return the rating the client gave after completion, or None."""
        for ev in self.history():
            if ev.get('rating') is not None:
                return ev.get('rating')
        return None

    def __repr__(self):
        return f'<MennemTrip {self.id} - {self.from_location} to {self.to_location} ({self.status})>'
