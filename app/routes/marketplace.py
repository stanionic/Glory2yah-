"""
Marketplace Routes Blueprint
AliExpress-style product browsing
"""
import traceback
from flask import Blueprint, render_template, request, jsonify, current_app, flash, redirect, url_for
from app.services.ad_service import AdService
from flask_login import current_user
from app.utils.validators import validate_pagination, sanitize_text, ValidationError

marketplace_bp = Blueprint('marketplace', __name__, url_prefix='/mache')


def _flush_approved_cache():
    """Clear Redis approved-ads cache to work around stale cache (pre-200eaea)."""
    try:
        from app.services.redis_service import RedisService
        from app import redis_client as rc
        rs = RedisService(rc)
        rs.invalidate_approved_ads()
        # Try delete individual known approved keys
        rs.cache_delete('ads:approved:list')
    except Exception:
        pass


def _safe_ad_to_dict(ad):
    """Robust version of ad.to_dict() — NEVER crashes on missing columns.

    Legacy databases on Render/SQLite may skip ALTER TABLE migrations and lack
    `quantity`, `publish_fee_gkach` columns. Accessing ad.publish_fee_gkach in
    those cases raises AttributeError → marketplace `except Exception` fallback
    silently returned products=[], creating the 'Pa gen pwodui' empty state
    even when approved rows exist in ads table.
    """
    try:
        # Try to use the real to_dict first
        return ad.to_dict()
    except Exception as top_err:
        import re
        # Build a minimal dict using getattr with defaults
        def _g(attr, default=None):
            try:
                v = getattr(ad, attr, default)
                return default if v is None else v
            except Exception:
                return default

        url = (_g('description', '') or '').strip() if _g('media_type') == 'url' else None
        video_id = None
        embed_url = None
        if url:
            yt = re.search(r'(?:youtube\.com\/(?:watch\?v=|shorts\/|embed\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})', url)
            if yt:
                video_id = yt.group(1)
                embed_url = f'https://www.youtube.com/embed/{video_id}?autoplay=1&mute=1&playsinline=1&rel=0&enablejsapi=1'
            else:
                vm = re.search(r'(?:vimeo\.com\/)([0-9]+)', url)
                if vm:
                    video_id = vm.group(1)
                    embed_url = f'https://player.vimeo.com/video/{video_id}?autoplay=1&muted=1&playsinline=1'

        d = {
            'id': _g('id'),
            'ad_id': _g('ad_id', ''),
            'user_whatsapp': _g('user_whatsapp', ''),
            'title': _g('title', ''),
            'description': _g('description', ''),
            'media_type': _g('media_type', 'images'),
            'images': [],
            'video': _g('video'),
            'video_id': video_id,
            'embed_url': embed_url,
            'ad_type': _g('ad_type', 'sell'),
            'price_gkach': _g('price_gkach', 0) or 0,
            'quantity': _g('quantity', None),
            'publish_fee_gkach': _g('publish_fee_gkach', 1000) or 1000,
            'category': _g('category') or 'other',
            'admin_status': _g('admin_status', 'under_review'),
            'payment_status': _g('payment_status', 'pending'),
            'like_count': _g('like_count', 0) or 0,
            'star_count': _g('star_count', 0) or 0,
            'view_count': _g('view_count', 0) or 0,
            'share_count': _g('share_count', 0) or 0,
            'created_at': None,
        }
        # quantity default
        if d['quantity'] is None:
            d['quantity'] = 1 if d['ad_type'] == 'sell' else 0
        # images list
        try:
            imgs = _g('images', '') or ''
            if imgs:
                d['images'] = [i.strip() for i in str(imgs).split(',') if i and i.strip()]
        except Exception:
            pass
        # created_at
        try:
            if ad.created_at is not None:
                d['created_at'] = ad.created_at.isoformat()
        except Exception:
            pass
        try:
            current_app.logger.warning(f"_safe_ad_to_dict fallback used for ad_id={d['ad_id']!r}: {type(top_err).__name__}: {top_err}")
        except Exception:
            pass
        return d


@marketplace_bp.route('/')
def index():
    """Marketplace homepage - AliExpress style grid"""
    # Always clear approved-ads cache on marketplace load
    # (stale sell-only cached data from pre-200eaea builds caused 'Pa gen pwodui')
    _flush_approved_cache()
    try:
        # Validate pagination parameters
        page, per_page = validate_pagination(
            request.args.get('page'),
            request.args.get('per_page'),
            max_per_page=current_app.config['MAX_ITEMS_PER_PAGE']
        )
        
        # Sanitize and validate category and sort_by
        category_raw = sanitize_text(request.args.get('category', 'all'))
        category = (category_raw or 'all').strip().lower() or 'all'
        sort_by_raw = sanitize_text(request.args.get('sort', 'recent'))
        sort_by = (sort_by_raw or 'recent').strip().lower() or 'recent'
        
        allowed_sorts = ['recent', 'price_low', 'price_high', 'popular']
        if sort_by not in allowed_sorts:
            sort_by = 'recent'

        # ALL approved ads appear in MACHE (sell + publish + jobs + services etc.)
        # BUGFIX 2026-08-06: previously `ad_type='sell'` exclusif was hiding
        # every approved announcement/publish/job/service ad.
        from app.models.ad import Ad
        query = Ad.query.filter_by(admin_status='approved')
        if category != 'all':
            query = query.filter_by(category=category)
        if sort_by == 'price_low':
            query = query.order_by(Ad.price_gkach.asc())
        elif sort_by == 'price_high':
            query = query.order_by(Ad.price_gkach.desc())
        elif sort_by == 'popular':
            query = query.order_by(Ad.view_count.desc())
        else:
            query = query.order_by(Ad.created_at.desc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        # SAFE convert to dict — NEVER raises (legacy DB missing columns)
        ads = []
        try:
            ads = [_safe_ad_to_dict(ad) for ad in pagination.items]
        except Exception as conv_err:
            current_app.logger.error(f"marketplace index() conversion inner exception: {conv_err}\n{traceback.format_exc()}")
            ads = []

        return render_template(
            'marketplace/index.html',
            products=ads,
            category=category,
            sort_by=sort_by,
            page=page,
            current_user=current_user
        )
    except ValidationError as e:
        flash(str(e), 'error')
        return redirect(url_for('marketplace.index'))
    except Exception as e:
        # CRITICAL: previously swallowed silently, empty products=[].
        # Log full stack trace for debugging in Render logs.
        current_app.logger.error(f"FATAL marketplace.index() exception: {e}\n{traceback.format_exc()}")
        return render_template(
            'marketplace/index.html',
            products=[],
            category='all',
            sort_by='recent',
            page=1,
            current_user=current_user
        )


@marketplace_bp.route('/api/products')
def api_products():
    """API endpoint for marketplace products (infinite scroll)"""
    from app.utils.validators import validate_pagination, sanitize_text, ValidationError
    _flush_approved_cache()
    try:
        page, per_page = validate_pagination(
            request.args.get('page'),
            request.args.get('per_page'),
            max_per_page=current_app.config['MAX_ITEMS_PER_PAGE']
        )

        category_raw = request.args.get('category', 'all') or 'all'
        category = category_raw.strip().lower()

        # ALL approved ads
        from app.models.ad import Ad
        query = Ad.query.filter_by(admin_status='approved')
        if category != 'all':
            query = query.filter_by(category=category)
        query = query.order_by(Ad.created_at.desc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        ads = []
        try:
            ads = [_safe_ad_to_dict(ad) for ad in pagination.items]
        except Exception as conv_err:
            current_app.logger.error(f"marketplace api_products() conversion inner exception: {conv_err}\n{traceback.format_exc()}")
            ads = []

        return jsonify({
            'success': True,
            'products': ads,
            'page': page,
            'has_more': len(ads) == per_page
        })
    except ValidationError as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"FATAL marketplace.api_products: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'products': []}), 500


@marketplace_bp.route('/search')
def search():
    """Search products in marketplace"""
    from app.utils.validators import validate_pagination, sanitize_text, ValidationError
    try:
        query = sanitize_text(request.args.get('q', ''))
        page, per_page = validate_pagination(
            request.args.get('page'),
            request.args.get('per_page'),
            max_per_page=current_app.config['MAX_ITEMS_PER_PAGE']
        )

        if not query:
            flash('Tanpri antre yon mo pou chèche.', 'info')
            return redirect(url_for('marketplace.index'))
        
        # Search using AdService
        results = AdService.search_ads(query, page=page, per_page=per_page)
        
        return render_template(
            'marketplace/search.html',
            products=results,
            query=query,
            page=page,
            current_user=current_user
        )
    except ValidationError as e:
        flash(str(e), 'error')
        return redirect(url_for('marketplace.index'))
    except Exception as e:
        current_app.logger.error(f"Error in marketplace search: {e}")
        return render_template(
            'marketplace/search.html',
            products=[],
            query=query,
            page=1,
            current_user=current_user
        )


@marketplace_bp.route('/categories')
def categories():
    """Browse by categories"""
    # Define product categories
    categories_list = [
        {'id': 'electronics', 'name': 'Elektwonik', 'icon': '📱'},
        {'id': 'fashion', 'name': 'Mòd', 'icon': '👗'},
        {'id': 'home', 'name': 'Kay', 'icon': '🏠'},
        {'id': 'beauty', 'name': 'Bote', 'icon': '💄'},
        {'id': 'sports', 'name': 'Espò', 'icon': '⚽'},
        {'id': 'food', 'name': 'Manje', 'icon': '🍔'},
        {'id': 'books', 'name': 'Liv', 'icon': '📚'},
        {'id': 'toys', 'name': 'Jwèt', 'icon': '🧸'},
        {'id': 'automotive', 'name': 'Machin', 'icon': '🚗'},
        {'id': 'other', 'name': 'Lòt', 'icon': '📦'},
    ]
    
    return render_template(
        'marketplace/categories.html',
        categories=categories_list,
        current_user=current_user
    )
