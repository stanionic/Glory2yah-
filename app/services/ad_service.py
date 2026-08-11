"""
Ad Service Layer
Business logic for classified ads
"""
from app import db
from app.models.ad import Ad
from app.utils.validators import validate_whatsapp, validate_amount, ValidationError
from app.services.redis_service import RedisService
from app import redis_client
import uuid


class AdService:
    """Service for Ad operations"""

    # ------------------------------------------------------------------
    # OpenGraph / Crawler preview helpers.
    #
    # HISTORICAL BUG CAUSE (Facebook showed generic logo instead of ad image):
    #   - Old code stored `ad.images` as a comma-separated STRING both in
    #     the Ad model column AND when dict-serialized into Redis cache.
    #   - Later Ad.to_dict() was fixed to return `images` as a Python LIST
    #     via Ad.get_images_list() (split + trim + reject empty).
    #   - BUT Redis cache entries written BEFORE the fix STILL contain the
    #     comma-separated STRING form. When a crawler (Facebook/WhatsApp)
    #     hits such a stale cached dict, Jinja templates do:
    #         og_images = ad.images          # STRING (truthy)
    #         og_first  = og_images[0]       # "p" (FIRST CHARACTER OF STRING!)
    #     → absolute_upload_url("p") → URL to a 404 → crawler falls back to
    #       the site logo, producing exactly the symptom the user reported:
    #       correct title/price but PREVIEW IMAGE = generic Glory2Yah banner.
    #
    # FIX STRATEGY (defense in depth, 3 layers):
    #   (A) HERE (Python/service layer) — repair `images` on every dict that
    #       crosses the AdService boundary (cache hits AND db to_dict()).
    #   (B) Jinja templates — normalize STRING→LIST in share_shortlink.html
    #       and ad_detail.html (catches any remaining dict we missed).
    #   (C) App startup — purge all `ad:*` Redis keys via
    #       AdService.invalidate_all_ad_caches() (one-time reset on deploy).
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_images_field(value):
        """Take `images` in any historical shape (str, list, None, junk) and
        always return a clean list[str] of image filenames.
          * None / empty / junk → []
          * str "a.jpg, b.jpg , , c.JPG" → ["a.jpg", "b.jpg", "c.JPG"]
          * list / tuple → trimmed, non-empty, strings-only, filtered for
            minimum plausible filename length (>= 4 chars AND contains ".").
        """
        import re as _re
        _safe_ext = lambda s: (
            isinstance(s, str)
            and len(s.strip()) >= 4
            and '.' in s
            and not _re.search(r'[^\w\-\. /+@]', s)  # conservative sanity
        )
        if value is None:
            return []
        if isinstance(value, (list, tuple)):
            out = []
            for item in value:
                if isinstance(item, str):
                    s = item.strip().replace('\\', '/')
                    if s.startswith('/'):
                        s = s.lstrip('/')
                    if _safe_ext(s):
                        out.append(s)
            return out
        if isinstance(value, str):
            s = value.strip()
            if not s:
                return []
            parts = [p.strip() for p in s.split(',')]
            out = []
            for p in parts:
                if not p:
                    continue
                pp = p.replace('\\', '/')
                if pp.startswith('/'):
                    pp = pp.lstrip('/')
                if _safe_ext(pp):
                    out.append(pp)
            return out
        # Anything else (int, dict, ...)
        return []

    @staticmethod
    def _repair_ad_dict_images(ad_dict):
        """Ensure the `images` key of a cached ad dict is ALWAYS a clean list.
        Mutates & returns the dict (idempotent, safe to call repeatedly)."""
        if not isinstance(ad_dict, dict):
            return ad_dict
        ad_dict['images'] = AdService._normalize_images_field(ad_dict.get('images'))
        # Ensure extra helper fields remain sane for templates:
        # Ad.get_first_image() equivalent on a dict (never raises).
        try:
            imgs = ad_dict.get('images') or []
            first = imgs[0] if imgs else None
            ad_dict.setdefault('first_image', first)
        except Exception:
            ad_dict['first_image'] = None
        return ad_dict
    
    @staticmethod
    def create_ad(user_whatsapp, title, description, media_type, images=None, 
                  video=None, ad_type='sell', price_gkach=0, category='other',
                  quantity=None):
        """Create new ad"""
        user_whatsapp = validate_whatsapp(user_whatsapp)
        
        if not title or len(title) < 3:
            raise ValidationError("Tit dwe gen omwen 3 karaktè")
        
        if not description or len(description) < 10:
            raise ValidationError("Deskripsyon dwe gen omwen 10 karaktè")
        
        if media_type not in ['images', 'video', 'text', 'url']:
            raise ValidationError("Tip medya envalid")
        
        # BUGFIX: validate ad_type strictly (was silently accepting any string)
        if ad_type not in ('sell', 'publish'):
            raise ValidationError("Tip piblisite envalid (dwe 'sell' oswa 'publish')")
        
        if ad_type == 'sell':
            price_gkach = validate_amount(price_gkach, min_amount=1)
            # Quantity: normalise for sell ads. Default = 1.
            try:
                q = int(quantity) if quantity is not None else 1
            except (ValueError, TypeError):
                q = 1
            if q < 1:
                q = 1
            quantity = q
        else:
            price_gkach = 0
            quantity = 0
        
        # Validate category against known list (fallback 'other')
        from app.utils.validators import sanitize_text
        valid_categories = {
            'electronics', 'fashion', 'home', 'beauty', 'sports',
            'food', 'books', 'toys', 'automotive', 'other'
        }
        category = sanitize_text(category, max_length=50) or 'other'
        if category not in valid_categories:
            category = 'other'
        
        ad = Ad(
            ad_id=str(uuid.uuid4()),
            user_whatsapp=user_whatsapp,
            title=title,
            description=description,
            media_type=media_type,
            images=images,
            video=video,
            ad_type=ad_type,
            price_gkach=price_gkach,
            quantity=quantity,
            category=category or 'other',
            admin_status='under_review',
            payment_status='pending'
        )
        
        db.session.add(ad)
        db.session.commit()
        
        return ad
    
    @staticmethod
    def get_ad(ad_id):
        """Get ad by ID with caching"""
        redis_service = RedisService(redis_client)
        
        # Try cache
        cache_key = f"ad:{ad_id}"
        cached_ad = redis_service.cache_get(cache_key)
        if cached_ad:
            return cached_ad
        
        # Query database
        ad = Ad.query.filter_by(ad_id=ad_id).first()
        if not ad:
            raise ValidationError("Piblisite pa jwenn")
        
        ad_data = ad.to_dict()
        
        # Cache for 10 minutes
        redis_service.cache_set(cache_key, ad_data, timeout=600)
        
        return ad_data
    
    @staticmethod
    def get_approved_ads(page=1, per_page=20):
        """Get approved ads with pagination"""
        redis_service = RedisService(redis_client)
        
        # Try cache for first page
        if page == 1:
            cached_ads = redis_service.get_approved_ads()
            if cached_ads:
                return cached_ads[:per_page]
        
        # Query database
        pagination = Ad.query.filter_by(
            admin_status='approved'
        ).order_by(
            Ad.created_at.desc()
        ).paginate(page=page, per_page=per_page, error_out=False)
        
        ads_data = [ad.to_dict() for ad in pagination.items]
        
        # Cache first page
        if page == 1:
            redis_service.set_approved_ads(ads_data, timeout=600)
        
        return ads_data
    
    @staticmethod
    def get_user_ads(whatsapp, page=1, per_page=20):
        """Get user's ads"""
        whatsapp = validate_whatsapp(whatsapp)
        
        pagination = Ad.query.filter_by(
            user_whatsapp=whatsapp
        ).order_by(
            Ad.created_at.desc()
        ).paginate(page=page, per_page=per_page, error_out=False)
        
        return [ad.to_dict() for ad in pagination.items]
    
    @staticmethod
    def approve_ad(ad_id):
        """Approve ad (admin only)"""
        ad = Ad.query.filter_by(ad_id=ad_id).first()
        if not ad:
            raise ValidationError("Piblisite pa jwenn")
        
        ad.admin_status = 'approved'
        db.session.commit()
        
        # Invalidate cache
        redis_service = RedisService(redis_client)
        redis_service.invalidate_approved_ads()
        redis_service.cache_delete(f"ad:{ad_id}")
        
        return ad
    
    @staticmethod
    def reject_ad(ad_id, reason=''):
        """Reject ad (admin only)"""
        ad = Ad.query.filter_by(ad_id=ad_id).first()
        if not ad:
            raise ValidationError("Piblisite pa jwenn")
        
        ad.admin_status = 'rejected'
        db.session.commit()
        
        # Invalidate cache
        redis_service = RedisService(redis_client)
        redis_service.cache_delete(f"ad:{ad_id}")
        
        return ad
    
    @staticmethod
    def update_ad(ad_id, user_whatsapp, title=None, description=None, 
                 price_gkach=None, images=None, video=None, quantity=None):
        """Update an existing ad (only owner can do this)"""
        ad = Ad.query.filter_by(ad_id=ad_id, user_whatsapp=user_whatsapp).first()
        if not ad:
            raise ValidationError("Piblisite pa jwenn oswa ou pa gen dwa modifye li")
        
        if title is not None and len(title) >= 3:
            ad.title = title
        if description is not None and len(description) >= 10:
            ad.description = description
        if price_gkach is not None and ad.ad_type == 'sell':
            price_gkach = validate_amount(price_gkach, min_amount=1)
            ad.price_gkach = price_gkach
        if quantity is not None and ad.ad_type == 'sell':
            try:
                q = int(quantity)
            except (ValueError, TypeError):
                q = None
            if q is not None and q >= 1:
                ad.quantity = q
        if images is not None:
            ad.images = images
        if video is not None:
            ad.video = video
        
        db.session.commit()
        
        # Invalidate cache
        redis_service = RedisService(redis_client)
        redis_service.invalidate_approved_ads()
        redis_service.cache_delete(f"ad:{ad_id}")
        
        return ad
    
    @staticmethod
    def delete_ad(ad_id, user_whatsapp=None):
        """Delete ad (only owner or admin can do this)"""
        query = Ad.query.filter_by(ad_id=ad_id)
        if user_whatsapp:
            query = query.filter_by(user_whatsapp=user_whatsapp)
        
        ad = query.first()
        if not ad:
            raise ValidationError("Piblisite pa jwenn oswa ou pa gen dwa efase li")
        
        db.session.delete(ad)
        db.session.commit()
        
        # Invalidate cache
        redis_service = RedisService(redis_client)
        redis_service.invalidate_approved_ads()
        redis_service.cache_delete(f"ad:{ad_id}")
        
        return True
    
    @staticmethod
    def increment_views(ad_id):
        """Increment ad view count"""
        ad = Ad.query.filter_by(ad_id=ad_id).first()
        if ad:
            ad.increment_views()
        return True
    
    @staticmethod
    def increment_likes(ad_id):
        """Increment ad like count"""
        ad = Ad.query.filter_by(ad_id=ad_id).first()
        if ad:
            ad.increment_likes()
        return True
    
    @staticmethod
    def increment_shares(ad_id):
        """Increment ad share count"""
        ad = Ad.query.filter_by(ad_id=ad_id).first()
        if ad:
            ad.increment_shares()
        return True
    
    @staticmethod
    def search_ads(query, page=1, per_page=20):
        """Search ads by title or description"""
        if not query or len(query) < 2:
            raise ValidationError("Rechèch dwe gen omwen 2 karaktè")
        
        pagination = Ad.query.filter(
            Ad.admin_status == 'approved',
            db.or_(
                Ad.title.ilike(f'%{query}%'),
                Ad.description.ilike(f'%{query}%')
            )
        ).order_by(
            Ad.created_at.desc()
        ).paginate(page=page, per_page=per_page, error_out=False)
        
        return [AdService._repair_ad_dict_images(ad.to_dict()) for ad in pagination.items]
    
    @staticmethod
    def get_stats():
        """Get ad statistics"""
        from sqlalchemy import func
        
        stats = {
            'total': Ad.query.count(),
            'approved': Ad.query.filter_by(admin_status='approved').count(),
            'pending': Ad.query.filter_by(admin_status='under_review').count(),
            'rejected': Ad.query.filter_by(admin_status='rejected').count(),
            'total_views': db.session.query(func.sum(Ad.view_count)).scalar() or 0,
            'total_likes': db.session.query(func.sum(Ad.like_count)).scalar() or 0,
            'total_shares': db.session.query(func.sum(Ad.share_count)).scalar() or 0,
        }
        
        return stats
    
    @staticmethod
    def invalidate_all_ad_caches():
        """Invalidate ALL ad-related caches (approved list + individual ads).
        Called at app startup to ensure freshly-approved ads are visible
        after a deploy/restart (Redis persists between deploys)."""
        from app.services.redis_service import RedisService
        from app import redis_client
        redis_service = RedisService(redis_client)
        
        # Invalidate the approved-ads list cache
        redis_service.invalidate_approved_ads()
        
        # Invalidate all individual ad caches (ad:<ad_id>)
        redis_service.cache_clear_pattern("ad:*")
