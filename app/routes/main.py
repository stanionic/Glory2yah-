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


@main_bp.route('/achte_gkach', methods=['GET', 'POST'])
def achte_gkach():
    """Page to request Gkach purchase"""
    if request.method == 'POST':
        from app import db
        from app.models.user_gkach import UserGkach
        from flask_login import current_user
        import uuid
        from datetime import datetime
        import os
        
        try:
            whatsapp = request.form.get('whatsapp', current_user.whatsapp if current_user.is_authenticated else '')
            amount = request.form.get('amount', 0)
            amount = int(amount) if amount else 0
            
            if not whatsapp or amount <= 0:
                flash('Veuillez fournir un numéro WhatsApp et un montant valides', 'danger')
                return redirect(url_for('main.achte_gkach'))
            
            # Get or create user gkach account
            account = UserGkach.query.filter_by(user_whatsapp=whatsapp).first()
            if not account:
                account = UserGkach(
                    user_whatsapp=whatsapp,
                    user_id=current_user.id if current_user.is_authenticated else None,
                    gkach_balance=0,
                    gkach_requests='[]'
                )
                db.session.add(account)
                db.session.commit()
            
            # Save request
            import json
            if not account.gkach_requests or account.gkach_requests == '[]':
                requests_list = []
            else:
                requests_list = json.loads(account.gkach_requests)
            
            new_request = {
                'request_id': str(uuid.uuid4()),
                'amount': amount,
                'status': 'pending',
                'requested_at': datetime.now().strftime('%d/%m/%Y %H:%M')
            }
            requests_list.append(new_request)
            
            account.gkach_requests = json.dumps(requests_list)
            db.session.commit()
            
            flash('Demann ou a voye avèk siksè! Administratè a pral kontakte w sou WhatsApp.', 'success')
            
            # Redirect to payment upload page
            return redirect(url_for('main.upload_gkach_approval', request_id=new_request['request_id']))
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error in achte_gkach: {e}")
            flash('Erè pandan soumisyon demann ou a.', 'danger')
    
    return render_template('achte_gkach.html')


@main_bp.route('/upload_gkach_approval/<request_id>', methods=['GET', 'POST'])
def upload_gkach_approval(request_id):
    """Upload payment proof for Gkach request"""
    from app.models.user_gkach import UserGkach
    from app import db
    import os
    import uuid
    
    if request.method == 'POST':
        try:
            # Find account with this request
            accounts = UserGkach.query.all()
            import json
            found_account = None
            target_request = None
            
            for account in accounts:
                if not account.gkach_requests or account.gkach_requests == '[]':
                    continue
                requests_list = json.loads(account.gkach_requests)
                for req in requests_list:
                    if req.get('request_id') == request_id:
                        found_account = account
                        target_request = req
                        break
                if found_account:
                    break
            
            if not found_account or not target_request:
                flash('Demann sa a pa jwenn.', 'danger')
                return redirect(url_for('main.achte_gkach'))
            
            # Save uploaded file
            if 'document' not in request.files:
                flash('Veuillez sélectionner un fichier.', 'danger')
                return redirect(request.url)
            
            file = request.files['document']
            if file.filename == '':
                flash('Veuillez sélectionner un fichier.', 'danger')
                return redirect(request.url)
            
            if file:
                ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'
                filename = f'gkach_req_{uuid.uuid4().hex}.{ext}'
                upload_path = os.path.join('static', 'uploads', filename)
                file.save(upload_path)
                
                # Update request with document
                requests_list = json.loads(found_account.gkach_requests)
                for i, req in enumerate(requests_list):
                    if req.get('request_id') == request_id:
                        requests_list[i]['document'] = filename
                        break
                
                found_account.gkach_requests = json.dumps(requests_list)
                db.session.commit()
                
                flash('Prèv pèman an telechaje avèk siksè!', 'success')
                return redirect(url_for('main.index'))
        
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error uploading gkach proof: {e}")
            flash('Erè pandan telechajman prèv pèman an.', 'danger')
    
    return render_template('upload_gkach_approval.html', request_id=request_id)


@main_bp.route('/api/gkach_rate')
def api_gkach_rate():
    """Get current Gkach exchange rate"""
    # Default rate: 1 GKach = 50 HTG
    return jsonify({'rate': 50})


@main_bp.route('/ad/<ad_id>')
def view_ad(ad_id):
    """View individual ad details (public route)"""
    try:
        ad = AdService.get_ad(ad_id)
        AdService.increment_views(ad_id)
        return render_template(
            'ad_detail.html',
            ad=ad,
            current_user=current_user
        )
    except Exception as e:
        flash(f'Piblisite pa jwenn: {str(e)}', 'error')
        return render_template('index.html', posts=[], marketplace_ads=[], current_user=current_user)


@main_bp.route('/submit_ad', methods=['GET', 'POST'])
def submit_ad():
    """Submit a new ad/post"""
    from flask_login import login_required, current_user
    from app.services.ad_service import AdService
    from app.utils.validators import validate_whatsapp, sanitize_text, ValidationError
    import os
    import uuid
    from flask import flash, redirect, url_for
    
    if request.method == 'POST':
        try:
            if not current_user.is_authenticated:
                flash('Ou dwe konekte pou soumèt yon piblisite!', 'error')
                return redirect(url_for('auth.login'))
                
            whatsapp = current_user.whatsapp
            media_type = request.form.get('media_type', 'images')
            ad_type = request.form.get('ad_type', 'publish')
            title = sanitize_text(request.form.get('title', ''))
            description = sanitize_text(request.form.get('description', ''))
            price_gkach = int(request.form.get('price_gkach', 0))
            
            # Handle file uploads
            images = []
            if media_type == 'images':
                for i in range(1, 4):
                    file_key = f'image_{i}'
                    if file_key in request.files:
                        file = request.files[file_key]
                        if file and file.filename:
                            # Save file
                            ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'
                            filename = f'{uuid.uuid4().hex}.{ext}'
                            upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                            file.save(upload_path)
                            images.append(filename)
                
            elif media_type == 'video':
                if 'video' in request.files:
                    file = request.files['video']
                    if file and file.filename:
                        ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'mp4'
                        filename = f'{uuid.uuid4().hex}.{ext}'
                        upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                        file.save(upload_path)
                        video = filename
                    else:
                        video = None
            else:
                video = None
            
            # Create the ad
            ad = AdService.create_ad(
                user_whatsapp=whatsapp,
                title=title,
                description=description,
                media_type=media_type,
                images=','.join(images) if images else None,
                video=video,
                ad_type=ad_type,
                price_gkach=price_gkach
            )
            
            flash('Piblisite soumèt avèk siksè! Li ap revize pa admin yo.', 'success')
            return redirect(url_for('auth.my_ads'))
            
        except ValidationError as e:
            flash(str(e), 'error')
        except Exception as e:
            current_app.logger.error(f"Error submitting ad: {e}")
            flash('Erè pandan soumèt piblisite a.', 'error')
    
    return render_template('submit_ad.html')


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
