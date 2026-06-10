"""
Batch Model - Grouped ads for viral sharing
"""
from app import db
from app.models.base import BaseModel


class Batch(BaseModel):
    """Batch of ads for viral sharing"""
    
    __tablename__ = 'batches'
    
    batch_id = db.Column(db.String(36), unique=True, nullable=False, index=True)
    ads = db.Column(db.Text, nullable=False)  # Comma-separated ad IDs
    
    # Metadata
    open_graph_data = db.Column(db.Text)
    facebook_share_url = db.Column(db.Text)
    
    # Engagement
    share_count = db.Column(db.Integer, default=0)
    click_rewards = db.Column(db.Integer, default=0)
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'batch_id': self.batch_id,
            'ads': self.ads.split(',') if self.ads else [],
            'share_count': self.share_count,
            'click_rewards': self.click_rewards,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
    
    def __repr__(self):
        return f'<Batch {self.batch_id}>'
