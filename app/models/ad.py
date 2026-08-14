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
    quantity = db.Column(db.Integer, default=1)

    # Category (marketplace browsing) — default 'other'
    category = db.Column(db.String(50), default='other', index=True)
    
    # Status
    admin_status = db.Column(db.String(20), default='under_review', index=True)
    # Status: under_review, approved, rejected
    payment_status = db.Column(db.String(20), default='pending', index=True)
    payment_proof = db.Column(db.String(255))
    publish_fee_gkach = db.Column(db.Integer, default=1000)
    
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
        CheckConstraint('quantity >= 0', name='check_positive_quantity'),
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
        """Convert to dictionary.

        embed_url generator supports:
          • YouTube (watch/shorts/embed/youtu.be/live/m/music/nocookie)
          • Vimeo  (player.vimeo.com with autoplay+muted+loop)
          • TikTok (www/@user/video/ID, vm.tiktok.com/SHORT via embed/v2)
          • Instagram (reel/reels/p/tv/{CODE})
          • Facebook / fb.watch / Meta Watch / video.php / groups posts

        All embeds include autoplay=1 + mute=1 + playsinline=1 + loop=1 so
        mobile browsers honor autoplay in viewport (cross-origin iframes
        refuse autoplay unless BOTH the iframe src opts-in AND the allow
        attribute has 'autoplay').
        """
        import re
        import urllib.parse as _urlp
        url = self.description.strip() if self.media_type == 'url' else None
        video_id = None
        embed_url = None
        if url:
            # ----- YouTube (all variants) -----
            yt_re = (
                r'(?:(?:https?:)?//)?'
                r'(?:www\.|m\.|music\.)?'
                r'(?:youtube(?:-nocookie)?\.com/'
                r'(?:watch\?(?:.*?&)?v=|shorts/|embed/|live/|v/)'
                r'|youtu\.be/)'
                r'([A-Za-z0-9_-]{11})'
            )
            m = re.search(yt_re, url)
            if m:
                vid = m.group(1)
                video_id = vid
                params = {
                    'autoplay': '1', 'mute': '1', 'playsinline': '1',
                    'rel': '0', 'enablejsapi': '1', 'modestbranding': '1',
                    'loop': '1', 'playlist': vid, 'hl': 'ht', 'cc_lang_pref': 'ht'
                }
                qs = _urlp.urlencode(params, safe='', quote_via=_urlp.quote)
                embed_url = f'https://www.youtube-nocookie.com/embed/{vid}?{qs}'

            # ----- Vimeo -----
            if not embed_url:
                vm_re = r'(?:https?:)?//(?:www\.)?vimeo\.com/(?:video/)?(\d+)'
                mv = re.search(vm_re, url)
                if mv:
                    vid = mv.group(1)
                    video_id = vid
                    params = {
                        'autoplay': '1', 'muted': '1', 'playsinline': '1',
                        'loop': '1', 'title': '0', 'byline': '0', 'portrait': '0',
                        'speed': '0', 'transparent': '0', 'background': '0'
                    }
                    qs = _urlp.urlencode(params)
                    embed_url = f'https://player.vimeo.com/video/{vid}?{qs}'

            # ----- TikTok (full URL /video/<id> OR vm.tiktok.com/SHORT) -----
            if not embed_url:
                tt_re = (
                    r'(?:https?:)?//(?:www\.)?tiktok\.com/'
                    r'(?:@[\w.]+/video|v)/([0-9A-Za-z]{8,25})'
                )
                mt = re.search(tt_re, url)
                if mt:
                    vid = mt.group(1)
                    video_id = vid
                    params = {'autoplay': '1', 'muted': 'true', 'playsinline': '1',
                              'loop': '1', 'controls': '1', 'enablejsapi': '1'}
                    qs = _urlp.urlencode(params)
                    embed_url = f'https://www.tiktok.com/embed/v2/{vid}?{qs}'
                else:
                    tt_short = r'(?:https?:)?//vm\.tiktok\.com/([A-Za-z0-9]{3,16})'
                    mts = re.search(tt_short, url)
                    if mts:
                        sc = mts.group(1)
                        video_id = sc
                        params = {'autoplay': '1', 'muted': 'true', 'playsinline': '1',
                                  'loop': '1', 'controls': '1', 'enablejsapi': '1'}
                        qs = _urlp.urlencode(params)
                        embed_url = f'https://www.tiktok.com/embed/v2/{sc}?{qs}'

            # ----- Instagram: reels/ p/ tv/ -----
            if not embed_url:
                ig_re = (
                    r'(?:https?:)?//(?:www\.)?instagram\.com/'
                    r'(reel|reels|p|tv)/([A-Za-z0-9_-]{5,})'
                )
                mi = re.search(ig_re, url)
                if mi:
                    kind = mi.group(1)
                    code = mi.group(2)
                    video_id = code
                    embed_url = (
                        f'https://www.instagram.com/{kind}/{code}/embed/'
                        f'?autoplay=1&mute=1&loop=1&playsinline=1&v=2'
                    )

            # ----- Facebook / Meta: watch/ video.php groups share fb.watch -----
            if not embed_url:
                fb_re = (
                    r'(?:https?:)?//(?:www\.|m\.|business\.)?'
                    r'(?:facebook|fb)\.com/'
                    r'(?:watch/?\?v=|video\.php\?v=|'
                    r'(?:[\w.%-]+/)?videos/|groups/[\w.%-]+/posts/|share/[vr]/|reel/|'
                    r'story\.php\?story_fbid=)'
                    r'(\d{5,})'
                )
                mf = re.search(fb_re, url)
                if mf:
                    vid = mf.group(1)
                    video_id = vid
                    fb_src = _urlp.quote(url, safe='')
                    params = {
                        'href': fb_src, 'show_captions': 'false',
                        'allowfullscreen': 'true', 'autoplay': '1', 'mute': '1',
                        'playsinline': '1', 'loop': '1'
                    }
                    qs = _urlp.urlencode(params)
                    embed_url = f'https://www.facebook.com/plugins/video.php?{qs}'
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
            'quantity': self.quantity if self.quantity is not None else (1 if self.ad_type == 'sell' else 0),
            'publish_fee_gkach': self.publish_fee_gkach if self.publish_fee_gkach is not None else 1000,
            'category': self.category or 'other',
            'admin_status': self.admin_status,
            'payment_status': self.payment_status,
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
