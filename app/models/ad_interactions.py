"""
Ad Interaction Models - Likes, Stars, Comments, Ratings
"""
from app import db
from app.models.base import BaseModel


class AdLike(BaseModel):
    """Model for tracking likes on ads"""
    __tablename__ = 'ad_likes'
    
    ad_id = db.Column(db.String(36), db.ForeignKey('ads.ad_id'), nullable=False, index=True)
    user_identifier = db.Column(db.String(50), nullable=False, index=True)
    
    # Relationships
    ad = db.relationship('Ad', backref='likes')


class AdStar(BaseModel):
    """Model for tracking stars/favorites on ads"""
    __tablename__ = 'ad_stars'
    
    ad_id = db.Column(db.String(36), db.ForeignKey('ads.ad_id'), nullable=False, index=True)
    user_identifier = db.Column(db.String(50), nullable=False, index=True)
    
    # Relationships
    ad = db.relationship('Ad', backref='stars')


class AdComment(BaseModel):
    """Model for comments on ads"""
    __tablename__ = 'ad_comments'
    
    ad_id = db.Column(db.String(36), db.ForeignKey('ads.ad_id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    comment = db.Column(db.Text, nullable=False)
    
    # Relationships
    ad = db.relationship('Ad', backref='comments')
    user = db.relationship('User', backref='ad_comments')


class AdRating(BaseModel):
    """Model for star ratings on ads"""
    __tablename__ = 'ad_ratings'
    
    ad_id = db.Column(db.String(36), db.ForeignKey('ads.ad_id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    rating = db.Column(db.Integer, nullable=False)  # 1-5 stars
    
    # Relationships
    ad = db.relationship('Ad', backref='ratings')
    user = db.relationship('User', backref='ad_ratings')
