"""
Marketplace Routes Blueprint
AliExpress-style product browsing
"""
from flask import Blueprint, render_template, request, jsonify, current_app, flash, redirect, url_for
from app.services.ad_service import AdService
from flask_login import current_user
from app.utils.validators import validate_pagination, sanitize_text, ValidationError

marketplace_bp = Blueprint('marketplace', __name__, url_prefix='/mache')


@marketplace_bp.route('/')
def index():
    """Marketplace homepage - AliExpress style grid"""
    try:
        # Validate pagination parameters
        page, per_page = validate_pagination(
            request.args.get('page'),
            request.args.get('per_page'),
            max_per_page=current_app.config['MAX_ITEMS_PER_PAGE']
        )
        
        # Sanitize and validate category and sort_by
        category = sanitize_text(request.args.get('category', 'all'))
        sort_by = sanitize_text(request.args.get('sort', 'recent'))
        
        allowed_sorts = ['recent', 'price_low', 'price_high', 'popular']
        if sort_by not in allowed_sorts:
            sort_by = 'recent' # Default to recent if invalid

        # BUGFIX: only 'sell' ads appear in the marketplace product grid
        # (social publish posts were polluting the grid with price-0 items).
        from app.models.ad import Ad
        query = Ad.query.filter_by(admin_status='approved', ad_type='sell')
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
        ads = [ad.to_dict() for ad in pagination.items]
        
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
        current_app.logger.error(f"Error in marketplace: {e}")
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
    try:
        page, per_page = validate_pagination(
            request.args.get('page'),
            request.args.get('per_page'),
            max_per_page=current_app.config['MAX_ITEMS_PER_PAGE']
        )
        
        category = request.args.get('category', 'all')
        
        # BUGFIX: only 'sell' ads in marketplace API (same as index())
        from app.models.ad import Ad
        query = Ad.query.filter_by(admin_status='approved', ad_type='sell')
        if category != 'all':
            query = query.filter_by(category=category)
        query = query.order_by(Ad.created_at.desc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        ads = [ad.to_dict() for ad in pagination.items]
        
        return jsonify({
            'success': True,
            'products': ads,
            'page': page,
            'has_more': len(ads) == per_page
        })
    except ValidationError as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"Error in marketplace API: {e}")
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
