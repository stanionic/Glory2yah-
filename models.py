from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Ad(db.Model):
    __tablename__ = 'ads'

    ad_id = db.Column(db.String(36), primary_key=True)
    user_whatsapp = db.Column(db.String(20), nullable=False)
    images = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text, nullable=False)
    title = db.Column(db.String(100))  # New title field
    payment_status = db.Column(db.String(20), default='pending')
    payment_proof = db.Column(db.String(255))
    admin_status = db.Column(db.String(20), default='under_review')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    batch_id = db.Column(db.String(36))
    price_gkach = db.Column(db.Integer, default=100)  # Price in Gkach coins

class Batch(db.Model):
    __tablename__ = 'batches'

    batch_id = db.Column(db.String(36), primary_key=True)
    ads = db.Column(db.Text, nullable=False)
    open_graph_data = db.Column(db.Text)
    facebook_share_url = db.Column(db.Text)
    share_count = db.Column(db.Integer, default=0)
    click_rewards = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class UserGkach(db.Model):
    __tablename__ = 'user_gkach'

    id = db.Column(db.Integer, primary_key=True)
    user_whatsapp = db.Column(db.String(20), nullable=False, unique=True)
    gkach_balance = db.Column(db.Integer, default=0)
    gkach_requests = db.Column(db.Text)  # JSON string for pending requests
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class GkachRate(db.Model):
    __tablename__ = 'gkach_rates'

    id = db.Column(db.Integer, primary_key=True)
    currency = db.Column(db.String(10), nullable=False, unique=True)  # e.g., 'HTG', 'USD'
    rate_per_gkach = db.Column(db.Float, nullable=False)  # How much currency per 1 Gkach
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
