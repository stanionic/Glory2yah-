"""
Main Routes Blueprint
Homepage and core pages
"""
import os
import random
import re
from flask import Blueprint, render_template, request, jsonify, current_app, flash
from app.services.ad_service import AdService
from app.services.redis_service import RedisService
from app import redis_client
from flask_login import current_user

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    """Homepage with Facebook-style feed and stories - Split layout with posts and ads carousel"""
    try:
        # Get posts for left side (social feed)
        posts = AdService.get_approved_ads(page=1, per_page=10)
        
        # Get ALL approved marketplace ads for carousel on right side
        from app.models.ad import Ad
        marketplace_ads = Ad.query.filter_by(admin_status='approved', ad_type='sell').order_by(Ad.created_at.desc()).all()
        marketplace_ads_dict = [ad.to_dict() for ad in marketplace_ads]
        
        return render_template(
            'index.html',
            posts=posts,
            marketplace_ads=marketplace_ads_dict,
            current_user=current_user
        )
    except Exception as e:
        current_app.logger.error(f"Error in index: {e}")
        return render_template(
            'index.html',
            posts=[],
            marketplace_ads=[],
            current_user=current_user
        )


@main_bp.route('/health')
def health_check():
    """Health check endpoint"""
    redis_service = RedisService(redis_client)
    
    health = {
        'status': 'healthy',
        'redis': redis_service.ping(),
        'database': True  # Will check DB connection
    }
    
    try:
        from app import db
        db.session.execute('SELECT 1')
        health['database'] = True
    except:
        health['database'] = False
        health['status'] = 'unhealthy'
    
    status_code = 200 if health['status'] == 'healthy' else 503
    return jsonify(health), status_code


@main_bp.route('/about')
def about():
    """About page"""
    return render_template('about.html')


@main_bp.route('/terms')
def terms():
    """Terms and conditions"""
    return render_template('terms.html')


@main_bp.route('/privacy')
def privacy():
    """Privacy policy"""
    return render_template('privacy.html')


@main_bp.route('/contact')
def contact():
    """Contact page"""
    return render_template('contact.html')


@main_bp.route('/api/stories')
def api_stories():
    """API endpoint for stories - loads random images from uploads folder"""
    try:
        upload_dir = os.path.join(current_app.root_path, '..', 'static', 'uploads')
        
        # Get all image files excluding payment and gkach proofs
        all_files = [f for f in os.listdir(upload_dir) 
                     if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')) 
                     and not f.startswith('payment_') 
                     and not f.startswith('gkach_')]
        
        # Select random 10 images for stories
        story_files = random.sample(all_files, min(10, len(all_files)))
        
        stories = []
        for i, filename in enumerate(story_files):
            stories.append({
                'id': i,
                'name': f'Story {i+1}',
                'image': f'/static/uploads/{filename}'
            })
        
        return jsonify({
            'success': True,
            'stories': stories
        })
    except Exception as e:
        current_app.logger.error(f"Error loading stories: {str(e)}")
        return jsonify({
            'success': False,
            'stories': []
        })


@main_bp.route('/api/feed')
def api_feed():
    """API endpoint for infinite scroll feed"""
    from app.utils.validators import validate_pagination, ValidationError
    try:
        page, per_page = validate_pagination(
            request.args.get('page'),
            request.args.get('per_page')
        )
    except ValidationError as e:
        current_app.logger.warning(f"Invalid pagination parameters: {e}")
        return jsonify({'success': False, 'message': str(e)}), 400
    
    try:
        ads = AdService.get_approved_ads(page=page, per_page=per_page)
        
        return jsonify({
            'success': True,
            'ads': ads,
            'page': page
        })
    except Exception as e:
        current_app.logger.error(f"Error in api_feed: {e}")
        return jsonify({'success': False, 'ads': []}), 500


@main_bp.route('/api/ads/<ad_id>/like', methods=['POST'])
def api_like_ad(ad_id):
    """API endpoint to like an ad"""
    try:
        AdService.increment_likes(ad_id)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False}), 500


@main_bp.route('/api/ads/<ad_id>/share', methods=['POST'])
def api_share_ad(ad_id):
    """API endpoint to track ad shares"""
    try:
        AdService.increment_shares(ad_id)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False}), 500


@main_bp.route('/api/gkach/balance')
def api_gkach_balance():
    """API endpoint to get user's Gkach balance"""
    if not current_user.is_authenticated:
        return jsonify({'balance': 0})
    
    try:
        balance = current_user.get_gkach_balance()
        return jsonify({'balance': balance})
    except Exception as e:
        return jsonify({'balance': 0})


@main_bp.route('/api/posts/create', methods=['POST'])
def create_post():
    """Create a text-only or URL post - 10MB max for text posts"""
    from app.models.ad import Ad
    from app import db
    import uuid
    from app.utils.validators import sanitize_text, validate_url, ValidationError
    
    if not current_user.is_authenticated:
        return jsonify({'success': False, 'message': 'Login required'}), 401
    
    # Ensure CSRF protection for this POST request
    # csrf.protect() # Assuming csrf is imported and initialized in app/__init__.py
    
    try:
        data = request.get_json()
        content = data.get('content', '').strip()
        post_type = data.get('type', 'text')  # 'text' or 'url'
        
        if not content:
            return jsonify({'success': False, 'message': 'Kontni obligatwa'}), 400
        content = sanitize_text(content)
        
        # Validate content size (10MB max for text)
        if post_type == 'text':
            content_size = len(content.encode('utf-8'))
            max_size = 10 * 1024 * 1024  # 10MB
            if content_size > max_size:
                raise ValidationError('Teks twò long (10MB max)')
        
        # Validate URL format for URL posts
        if post_type == 'url':
            content = validate_url(content) # Will raise ValidationError if invalid
            
        
        # Create new post
        post_id = str(uuid.uuid4())
        
        new_post = Ad(
            ad_id=post_id,
            user_whatsapp=current_user.whatsapp,
            title=f"Post {'Teks' if post_type == 'text' else 'Liyen'}",
            description=content,
            media_type='text' if post_type == 'text' else 'url',
            ad_type='publish',  # Social post, not for sale
            price_gkach=0,
            admin_status='approved',  # Auto-approve text/URL posts
            payment_status='completed'
        )
        
        db.session.add(new_post)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Post kreye ak siksè!',
            'post': new_post.to_dict()
        })
        
    except ValidationError as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating post: {e}")
        return jsonify({'success': False, 'message': 'Erè pandan kreyasyon post'}), 500


@main_bp.route('/api/posts/preview-url', methods=['POST'])
def preview_url():
    """Preview URL metadata for auto-display"""
    from app.utils.validators import validate_url, ValidationError, sanitize_text
    import requests
    from bs4 import BeautifulSoup
    
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        
        # Validate and sanitize URL
        url = validate_url(url)
        
        # Fetch URL content
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract metadata
        metadata = {
            'title': '',
            'description': '',
            'image': '',
            'site_name': '',
            'url': url
        }
        
        # Try to get Open Graph tags first
        og_title = soup.find('meta', property='og:title')
        if og_title:
            metadata['title'] = og_title.get('content', '')
        
        og_description = soup.find('meta', property='og:description')
        if og_description:
            metadata['description'] = og_description.get('content', '')
        
        og_image = soup.find('meta', property='og:image')
        if og_image:
            metadata['image'] = og_image.get('content', '')
        
        og_site_name = soup.find('meta', property='og:site_name')
        if og_site_name:
            metadata['site_name'] = og_site_name.get('content', '')
        
        # Fallback to regular tags if no OG tags
        if not metadata['title']:
            title_tag = soup.find('title')
            if title_tag:
                metadata['title'] = title_tag.get_text()
        
        if not metadata['description']:
            desc_tag = soup.find('meta', attrs={'name': 'description'})
            if desc_tag:
                metadata['description'] = desc_tag.get('content', '')
        
        # Extract domain for site_name if still missing
        if not metadata['site_name']:
            domain_match = re.search(r'https?://([^/]+)', url)
            if domain_match:
                metadata['site_name'] = domain_match.group(1)
        
        # Clean up the data
        metadata['title'] = sanitize_text(metadata['title'], max_length=100) or 'Pa gen tit'
        metadata['description'] = sanitize_text(metadata['description'], max_length=200) or 'Pa gen deskripsyon'
        
        return jsonify({
            'success': True,
            'metadata': metadata
        })
        
    except ValidationError as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    except requests.RequestException as e:
        return jsonify({'success': False, 'message': 'Pa ka aksede URL la'}), 400
    except Exception as e:
        current_app.logger.error(f"Error previewing URL: {e}")
        return jsonify({'success': False, 'message': 'Erè pandan preview URL'}), 500
