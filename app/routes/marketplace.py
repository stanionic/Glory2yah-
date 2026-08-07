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


# #region debug-point A:marketplace-index-entry
# Instrumentation: reports entry/exit counts, category filter, product count,
# fallback usage counts to Debug Server (local NDJSON fallback if server down)
import json as _dbg_json, os as _dbg_os, threading as _dbg_thr, time as _dbg_time
_DBG_P = '.dbg/marketplace-approved-ads-empty-state.env'
_DBG_U, _DBG_S = 'http://127.0.0.1:7777/event', 'marketplace-approved-ads-empty-state'
try:
    with open(_DBG_P) as _dbg_f:
        _dbg_c = _dbg_f.read()
        for _dbg_l in _dbg_c.split('\n'):
            if _dbg_l.startswith('DEBUG_SERVER_URL='): _DBG_U = _dbg_l.split('=',1)[1].strip()
            elif _dbg_l.startswith('DEBUG_SESSION_ID='): _DBG_S = _dbg_l.split('=',1)[1].strip()
except Exception:
    pass
_DBG_LOCK = _dbg_thr.Lock()
_DBG_NDJSON = '.dbg/trae-debug-log-marketplace-approved-ads-empty-state.ndjson'
def _dbg_log(hypothesisId, msg, data=None, runId='post', location='marketplace.py'):
    """Report debug event to Debug Server HTTP, else append locally to NDJSON."""
    try:
        import urllib.request as _ur
        payload = {
            'sessionId': _DBG_S, 'runId': runId, 'hypothesisId': hypothesisId,
            'location': location, 'msg': '[DEBUG] '+msg,
            'data': data or {}, 'ts': int(_dbg_time.time()*1000)
        }
        body = _dbg_json.dumps(payload).encode()
        try:
            req = _ur.Request(_DBG_U, data=body, headers={'Content-Type':'application/json'})
            _ur.urlopen(req, timeout=1).read()
            return
        except Exception:
            pass
        # Fallback: write NDJSON locally
        with _DBG_LOCK:
            os.makedirs('.dbg', exist_ok=True)
            with open(_DBG_NDJSON, 'a', encoding='utf-8') as f:
                f.write(_dbg_json.dumps(payload)+'\n')
    except Exception:
        pass
# #endregion


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
            'video_url': None,
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
        # video_url: resolve full upload URL
        try:
            _vname = d.get('video')
            if _vname:
                try:
                    from flask import url_for as _uf2
                    d['video_url'] = _uf2('static', filename='uploads/' + str(_vname))
                except Exception:
                    d['video_url'] = '/static/uploads/' + str(_vname)
        except Exception:
            pass
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
    # #region debug-point A:marketplace-index-entry (H1-H5)
    _dbg_log('A', 'index() entry; flushing approved cache OK', {'route':'/mache/'}, location='marketplace.py:index')
    # #endregion
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

        # ONLY ADS WITH ad_type='sell' (VANN) and admin_status='approved' are displayed
        # in MACHE. Annonces 'publish' (PIBLIYE SELMAN) stay in the social feed only.
        # (Fix 2026-08-07: previously ALL approved ads (sell+publish+services) polluted Mache
        #  and real sell products got pushed off-screen / hidden.)
        from app.models.ad import Ad
        query = Ad.query.filter_by(admin_status='approved', ad_type='sell')
        # #region debug-point B:check-filter-chain (H2 H5)
        from sqlalchemy import func as _sa_func
        try:
            total_db_approved = Ad.query.filter_by(admin_status='approved').count() or 0
            total_db_sell_approved = Ad.query.filter_by(admin_status='approved', ad_type='sell').count() or 0
            total_db_publish_approved = Ad.query.filter_by(admin_status='approved', ad_type='publish').count() or 0
        except Exception:
            total_db_approved = total_db_sell_approved = total_db_publish_approved = -1
        _dbg_log('B', 'base query: ONLY (admin_status=approved, ad_type=sell). pre-filter chain.',
                 {'category': category, 'sort_by': sort_by, 'page': page, 'per_page': per_page,
                  'db_approved_total': total_db_approved,
                  'db_approved_sell': total_db_sell_approved,
                  'db_approved_publish': total_db_publish_approved},
                 location='marketplace.py:index:pre-filter-sell-only')
        # #endregion
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
            # #region debug-point D:safe-conversion-exception (H4)
            _dbg_log('D', 'conversion inner exception (pagination items iter)',
                     {'conv_err': str(conv_err), 'pagination_items_len': len(pagination.items)},
                     location='marketplace.py:index:conv-exc')
            # #endregion
            ads = []

        # #region debug-point A:index-exit-success (H1 H2 H5)
        from collections import Counter as _Cnt
        types_cnt = dict(_Cnt(a.get('ad_type','?') for a in ads))
        cats_cnt = dict(_Cnt(a.get('category','?') for a in ads))
        _dbg_log('A', f'index() exit success: ads.len={len(ads)}; types={types_cnt}; categories={cats_cnt}',
                 {'products_len': len(ads), 'per_type': types_cnt, 'per_category': cats_cnt,
                  'category': category, 'sort_by': sort_by, 'total_count': pagination.total},
                 location='marketplace.py:index:exit-ok')
        # #endregion
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
        # #region debug-point A:index-exit-fatal (H4)
        _dbg_log('A', f'index() FATAL exception swallowed — would return products=[]',
                 {'exception': str(e), 'stack': traceback.format_exc()[:800]},
                 location='marketplace.py:index:exit-fatal')
        # #endregion
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

        # ONLY ADS SELL+APPROVED go in Mache (publish stays in feed). Same filter as index().
        from app.models.ad import Ad
        query = Ad.query.filter_by(admin_status='approved', ad_type='sell')
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
