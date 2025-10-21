from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Ad(db.Model):
    __tablename__ = 'ads'

    ad_id = db.Column(db.String(36), primary_key=True)
    user_whatsapp = db.Column(db.String(20), nullable=False)
    images = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text, nullable=False)
    payment_status = db.Column(db.String(20), default='pending')
    payment_proof = db.Column(db.String(255))
    admin_status = db.Column(db.String(20), default='under_review')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    batch_id = db.Column(db.String(36))

class Batch(db.Model):
    __tablename__ = 'batches'

    batch_id = db.Column(db.String(36), primary_key=True)
    ads = db.Column(db.Text, nullable=False)
    open_graph_data = db.Column(db.Text)
    facebook_share_url = db.Column(db.Text)
    share_count = db.Column(db.Integer, default=0)
    click_rewards = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
