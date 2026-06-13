"""
BatchAd Junction Model
Links Ads to Batches for normalized many-to-many relationship
"""
from app import db
from datetime import datetime

class BatchAd(db.Model):
    __tablename__ = 'batch_ads'
    
    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.String(36), db.ForeignKey('batches.batch_id', ondelete='CASCADE'), nullable=False)
    ad_id = db.Column(db.String(36), db.ForeignKey('ads.ad_id', ondelete='CASCADE'), nullable=False)
    position = db.Column(db.Integer, default=0)  # Preserves the order of ads in the batch
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Ensure an ad isn't duplicated within the same batch
    __table_args__ = (db.UniqueConstraint('batch_id', 'ad_id', name='_batch_ad_uc'),)