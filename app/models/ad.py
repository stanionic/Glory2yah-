"""
Ad Model - Classified Ads with Redis caching
"""
from app import db
from app.models.base import BaseModel
from sqlalchemy import CheckConstraint


class Ad(BaseModel):
    """Advertisement model"""
    
    __tablename__ = 'ads'
    
    ad_id = db.Column(db.String(36), unique=True, nullable=False, index=True)
    user_whatsapp = db.Column(db.String(20), nullable=False, index=True)
    
    # Content
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    
    # Media
    media_type = db.Column(db.String(10), nullable=False, default='images')  # images, video
    images = db.Column(db.Text)  # Comma-separated filenames
    video = db.Column(db.String(255))
    
    # Type & Pricing
    ad_type = db.Column(db.String(10), nullable=False, default='sell')  # publish, sell
    price_gkach = db.Column(db.Integer, default=0)
    
    # Status
    admin_status = db.Column(db.String(20), default='under_review', index=True)
    # Status: under_review, approved, rejected
    payment_status = db.Column(db.String(20), default='pending', index=True)
    payment_proof = db.Column(db.String(255))
    
    # Batch
    batch_id = db.Column(db.String(36), index=True)
    
    # Engagement
    like_count = db.Column(db.Integer, default=0)
    star_count = db.Column(db.Integer, default=0)
    view_count = db.Column(db.Integer, default=0)
    share_count = db.Column(db.Integer, default=0)
    average_rating = db.Column(db.Float, default=0.0)
    rating_count = db.Column(db.Integer, default=0)
    
    # Constraints
    __table_args__ = (
        CheckConstraint('price_gkach >= 0', name='check_positive_price'),
    )
    
    def get_images_list(self):
        """Get list of image filenames"""
        if not self.images:
            return []
        return [img.strip() for img in self.images.split(',') if img.strip()]
    
    def get_first_image(self):
        """Get first image filename"""
        images = self.get_images_list()
        return images[0] if images else None
    
    def increment_views(self):
        """Increment view count"""
        self.view_count += 1
        db.session.commit()
        
        # Update cache
        self._invalidate_cache()
    
    def increment_likes(self):
        """Increment like count"""
        self.like_count += 1
        db.session.commit()
        self._invalidate_cache()
    
    def increment_shares(self):
        """Increment share count"""
        self.share_count += 1
        db.session.commit()
        self._invalidate_cache()
    
    def _invalidate_cache(self):
        """Invalidate related caches"""
        from app.services.redis_service import RedisService
        from app import redis_client
        
        redis_service = RedisService(redis_client)
        redis_service.invalidate_approved_ads()
        redis_service.cache_delete(f"ad:{self.ad_id}")
    
    def to_dict(self):
        """Convert to dictionary"""
        import re
        url = self.description.strip() if self.media_type == 'url' else None
        video_id = None
        embed_url = None
        if url:
            youtube_regex = r'(?:youtube\.com\/(?:watch\?v=|shorts\/|embed\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})'
            youtube_match = re.search(youtube_regex, url)
            if youtube_match:
                video_id = youtube_match.group(1)
                embed_url = f'https://www.youtube.com/embed/{video_id}?autoplay=1&mute=1'
            else:
                vimeo_regex = r'(?:vimeo\.com\/)([0-9]+)'
                vimeo_match = re.search(vimeo_regex, url)
                if vimeo_match:
                    video_id = vimeo_match.group(1)
                    embed_url = f'https://player.vimeo.com/video/{video_id}?autoplay=1&muted=1'
        return {
            'id': self.id,
            'ad_id': self.ad_id,
            'user_whatsapp': self.user_whatsapp,
            'title': self.title,
            'description': self.description,
            'media_type': self.media_type,
            'images': self.get_images_list(),
            'video': self.video,
            'video_id': video_id,
            'embed_url': embed_url,
            'ad_type': self.ad_type,
            'price_gkach': self.price_gkach,
            'admin_status': self.admin_status,
            'like_count': self.like_count,
            'star_count': self.star_count,
            'view_count': self.view_count,
            'share_count': self.share_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
    
    @classmethod
    def get_approved_ads(cls, limit=None):
        """Get approved ads with caching"""
        from app.services.redis_service import RedisService
        from app import redis_client
        
        redis_service = RedisService(redis_client)
        
        # Try cache
        cached_ads = redis_service.get_approved_ads()
        if cached_ads:
            return cached_ads
        
        # Query database
        query = cls.query.filter_by(admin_status='approved').order_by(cls.created_at.desc())
        if limit:
            query = query.limit(limit)
        
        ads = query.all()
        ads_data = [ad.to_dict() for ad in ads]
        
        # Cache for 10 minutes
        redis_service.set_approved_ads(ads_data, timeout=600)
        
        return ads_data
    
    def __repr__(self):
        return f'<Ad {self.ad_id}: {self.title}>'
