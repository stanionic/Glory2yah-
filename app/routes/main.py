"""
Main Routes Blueprint
Homepage and core pages
"""
import os
import random
import re
from flask import Blueprint, render_template, request, jsonify, current_app, flash, redirect, url_for
from app.services.ad_service import AdService
from app.services.redis_service import RedisService
from app import redis_client
from flask_login import current_user, login_required
from app.models.admin_settings import AdminSettings
from app.services.gkach_service import GkachService
from datetime import datetime
from flask import request as flask_req

main_bp = Blueprint('main', __name__)


@main_bp.route('/search', methods=['GET'])
def search():
    """P1 FIX B02 — dispatcher for base.html <form action="/search"> (404 before)"""
    try:
        q = (request.args.get('q') or '').strip()
        category = (request.args.get('category') or '').strip()
        location = (request.args.get('location') or '').strip()
        try:
            return redirect(url_for('marketplace.index', q=q, category=category, location=location))
        except Exception:
            posts = []
            if q:
                from app.models.ad import Ad
                like = f"%{q}%"
                posts = Ad.query.filter(
                    Ad.admin_status == 'approved',
                    db.or_(Ad.title.ilike(like), Ad.description.ilike(like))
                ).order_by(Ad.created_at.desc()).limit(50).all()
            return render_template('index.html', posts=posts or [], marketplace_ads=[], current_user=current_user)
    except Exception as e:
        current_app.logger.error(f"Search error: {e}")
        return redirect(url_for('main.index'))


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


@main_bp.route('/tv')
def tv():
    # Check if user has a session start time
    from flask import session
    if 'gadematch_start' not in session:
        session['gadematch_start'] = datetime.now().isoformat()
    
    # Calculate time elapsed
    start_time = datetime.fromisoformat(session['gadematch_start'])
    elapsed = (datetime.now() - start_time).total_seconds() / 60  # in minutes
    
    # Fetch admin settings for popup configuration
    admin_settings = AdminSettings.get_all_settings()
    enable_gkach_notice = admin_settings.get('enable_gkach_notice') == 'True'
    gkach_required_amount = int(admin_settings.get('gkach_required_amount', 1000))
    gkach_target_date_str = admin_settings.get('gkach_target_date', '2026-06-20')
    gkach_target_date = datetime.strptime(gkach_target_date_str, '%Y-%m-%d') if gkach_target_date_str else datetime(2026, 6, 20)

    current_time = datetime.now()

    # Check if user is logged in
    if not current_user.is_authenticated:
        # If not logged in and time is up (over 45 minutes)
        if elapsed > 45:
            flash('Ou dwe konekte pou kontinye gade GADE MATCH!', 'error')
            return redirect(url_for('auth.login'))
    
    # If Gkach notice is enabled and conditions are met
    if current_user.is_authenticated and enable_gkach_notice and current_time < gkach_target_date and current_user.get_gkach_balance() < gkach_required_amount:
        flash(f'Aksè a GADE MATCH mande {gkach_required_amount} GKACH anvan {gkach_target_date.strftime("%d %b %Y")}. Tanpri achte GKACH.', 'error')
        return redirect(url_for('main.index'))  # Redirect to index to show GKACH popup

    return render_template('tv.html', 
                           is_logged_in=current_user.is_authenticated,
                           gkach_balance=current_user.get_gkach_balance() if current_user.is_authenticated else 0,
                           admin_settings=admin_settings)


@main_bp.route('/gadematch')
def gadematch():
    # Check if user has a session start time
    from flask import session
    if 'gadematch_start' not in session:
        session['gadematch_start'] = datetime.now().isoformat()
    
    # Calculate time elapsed
    start_time = datetime.fromisoformat(session['gadematch_start'])
    elapsed = (datetime.now() - start_time).total_seconds() / 60  # in minutes
    
    # Fetch admin settings for popup configuration
    admin_settings = AdminSettings.get_all_settings()
    enable_gkach_notice = admin_settings.get('enable_gkach_notice') == 'True'
    gkach_required_amount = int(admin_settings.get('gkach_required_amount', 1000))
    gkach_target_date_str = admin_settings.get('gkach_target_date', '2026-06-20')
    gkach_target_date = datetime.strptime(gkach_target_date_str, '%Y-%m-%d') if gkach_target_date_str else datetime(2026, 6, 20)

    current_time = datetime.now()

    # Check if user is logged in
    if not current_user.is_authenticated:
        # If not logged in and time is up (over 45 minutes)
        if elapsed > 45:
            flash('Ou dwe konekte pou kontinye gade GADE MATCH!', 'error')
            return redirect(url_for('auth.login'))
    
    # If Gkach notice is enabled and conditions are met
    if current_user.is_authenticated and enable_gkach_notice and current_time < gkach_target_date and current_user.get_gkach_balance() < gkach_required_amount:
        flash(f'Aksè a GADE MATCH mande {gkach_required_amount} GKACH anvan {gkach_target_date.strftime("%d %b %Y")}. Tanpri achte GKACH.', 'error')
        return redirect(url_for('main.index'))  # Redirect to index to show GKACH popup

    return render_template('tv.html', 
                           is_logged_in=current_user.is_authenticated,
                           gkach_balance=current_user.get_gkach_balance() if current_user.is_authenticated else 0,
                           admin_settings=admin_settings)


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
    """API endpoint for stories"""
    try:
        from app.models.story import Story
        stories = Story.query.filter_by(admin_status='approved').order_by(Story.created_at.desc()).all()
        stories_dict = [story.to_dict() for story in stories]
        
        return jsonify({
            'success': True,
            'stories': stories_dict
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


@main_bp.route('/api/ads/trending')
def api_ads_trending():
    """API endpoint for trending ads"""
    try:
        from app.models.ad import Ad
        trending = Ad.query.filter_by(admin_status='approved').order_by(Ad.view_count.desc()).limit(10).all()
        return jsonify({
            'success': True,
            'ads': [ad.to_dict() for ad in trending]
        })
    except Exception as e:
        current_app.logger.error(f"Error in api_ads_trending: {e}")
        return jsonify({'success': False, 'ads': []}), 500


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
            
            # Check for file upload
            if 'document' not in request.files:
                flash('Veuillez télécharger un document de preuve de paiement.', 'danger')
                return redirect(url_for('main.achte_gkach'))
            
            file = request.files['document']
            if file.filename == '':
                flash('Veuillez télécharger un document de preuve de paiement.', 'danger')
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
            
            # Save uploaded file
            ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'
            filename = f'gkach_req_{uuid.uuid4().hex}.{ext}'
            upload_path = os.path.join('static', 'uploads', filename)
            file.save(upload_path)
            
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
                'document': filename,
                'requested_at': datetime.now().strftime('%d/%m/%Y %H:%M')
            }
            requests_list.append(new_request)
            
            account.gkach_requests = json.dumps(requests_list)
            db.session.commit()
            
            flash('Demann ou a voye avèk siksè ak dokiman prèv! Administratè a pral kontakte w sou WhatsApp.', 'success')
            
            # Redirect to home or success page
            return redirect(url_for('main.index'))
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error in achte_gkach: {e}")
            flash('Erè pandan soumisyon demann ou a.', 'danger')
    
    return render_template('achte_gkach.html')


# =========================================================================
# ADS PUBLISH PAYMENT FLOW
# =========================================================================
# Every published ad costs ADS_PUBLISH_FEE = 1000 Gkach.
#   - Flow: submit_ad() creates Ad (payment_status='pending')
#           -> redirects HERE so user uploads Moncash/Netcash proof
#           -> admin panel sets payment_status='verified'
#           -> THEN admin can set admin_status='approved'
#              (guarded in admin.py update_ad_status())
# =========================================================================
ADS_PUBLISH_FEE = 1000


@main_bp.route('/upload_payment/<ad_id>', methods=['GET', 'POST'])
@login_required
def upload_payment(ad_id):
    """Upload Moncash/Netcash screenshot proof to pay for an ad publication.

    * Always enforces ADS_PUBLISH_FEE (1000 Gkach) regardless of what the
      client sends.
    * Owner-only: redirects to my_ads if someone tries to upload proof for
      an ad that isn't theirs.
    * After upload: payment_status stays 'pending' (admin must manually
      mark 'verified' / 'rejected'). This prevents auto-approval scams.
    """
    from app import db
    from app.models.ad import Ad
    import uuid

    ad = Ad.query.filter_by(ad_id=ad_id).first()
    if not ad:
        flash('Piblisite sa a pa egziste.', 'error')
        return redirect(url_for('auth.my_ads'))

    if ad.user_whatsapp != current_user.whatsapp:
        flash('Ou pa gen dwa modifye piblisite lòt moun!', 'error')
        return redirect(url_for('auth.my_ads'))

    # Lock-in the publication fee (always 1000 Gkach) for backwards compat
    # with rows created before the column existed.
    if not ad.publish_fee_gkach or ad.publish_fee_gkach <= 0:
        ad.publish_fee_gkach = ADS_PUBLISH_FEE
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

    fee = int(ad.publish_fee_gkach or ADS_PUBLISH_FEE)
    rate = float(current_app.config.get('GKACH_TO_HTG_RATE', 1.2) or 1.2)
    fee_htg = round(float(fee) * rate, 2)

    if request.method == 'POST':
        try:
            accept_terms = request.form.get('accept_terms', '')
            if str(accept_terms).lower() not in ('on', 'true', '1', 'yes', 'oui'):
                raise ValueError(
                    "Ou dwe li epi aksepte Kondisyon ak Règleman anvan ou voye prèv la."
                )

            if 'payment_proof' not in request.files:
                raise ValueError('Tanpri chwazi yon fichye prèv pèman (screenshot).')

            file = request.files['payment_proof']
            if not file or not file.filename:
                raise ValueError('Tanpri chwazi yon fichye prèv pèman.')

            ext = (
                file.filename.rsplit('.', 1)[-1].lower()
                if '.' in file.filename else 'jpg'
            )
            if ext not in {'jpg', 'jpeg', 'png', 'gif', 'webp', 'pdf'}:
                raise ValueError('Fòma fichye pa aksepte. Itilize JPG, PNG, GIF, PDF oswa WEBP.')

            upload_folder = os.path.join(
                current_app.root_path, '..', current_app.config['UPLOAD_FOLDER']
            )
            upload_folder = os.path.abspath(upload_folder)
            os.makedirs(upload_folder, exist_ok=True)

            filename = f'pay_proof_{uuid.uuid4().hex}.{ext}'
            dest = os.path.join(upload_folder, filename)
            file.save(dest)

            ad.payment_proof = filename
            # Keep 'pending': admin must flip to 'verified' manually.
            ad.payment_status = 'pending'
            db.session.commit()

            # Notify admin via notification helper if available.
            try:
                from src.notifications import notify_admin_payment_proof_uploaded
                notify_admin_payment_proof_uploaded(ad.user_whatsapp, ad.ad_id)
            except Exception:
                pass

            flash(
                f'Prèv pèman an resevwa! (FRAI: {fee} Gkach = {fee_htg:.2f} HTG). '
                f'Administratè a pral verifye l pa WhatsApp epi mete estati piblisite w la ajou.',
                'success'
            )
            return redirect(url_for('auth.my_ads'))

        except ValueError as e:
            flash(str(e), 'error')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'upload_payment failed ad_id={ad_id}: {e}')
            flash('Erè pandan w ap telechaje prèv pèman an. Reeseye.', 'error')

    return render_template(
        'upload_payment.html',
        ad=ad,
        fee_gkach=fee,
        fee_htg=fee_htg,
    )


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
    from flask import current_app
    rate = current_app.config.get('GKACH_TO_HTG_RATE', 1.2)
    return jsonify({'rate': rate})


@main_bp.route('/ad/<ad_id>')
def view_ad(ad_id):
    """View individual ad details (public route)"""
    try:
        # BUGFIX: increment views FIRST, then read the fresh dict so the page
        # shows the updated count (previously the stale pre-increment count was
        # rendered because get_ad() was called before increment_views()).
        AdService.increment_views(ad_id)
        ad = AdService.get_ad(ad_id)
        return render_template(
            'ad_detail.html',
            ad=ad,
            current_user=current_user
        )
    except Exception as e:
        current_app.logger.error(f"view_ad failed for ad_id={ad_id}: {e}")
        flash('Piblisite sa a pa jwenn.', 'error')
        return render_template('index.html', posts=[], marketplace_ads=[], current_user=current_user)


@main_bp.route('/submit_ad', methods=['GET', 'POST'])
def submit_ad():
    """Submit a new ad/post.

    Frontend (submit_ad.html) provides:
      - `price_gourdes` : the HTG value the user types in (if ad_type == 'sell')
      - `price_gkach`   : a hidden input, updated from HTG by client-side JS
                          (falls back to `0` if JS is disabled / errors / client
                          rate-mismatch).
    Backend therefore MUST recompute `price_gkach` from `price_gourdes`
    using the authoritative app rate GKACH_TO_HTG_RATE whenever ad_type=sell
    and the hidden input is still zero. Also enforces required-field guards
    that match the HTML5 `required` attributes so submit never fails silently
    when someone bypasses client-side validation.
    """
    from flask_login import login_required, current_user
    from app.services.ad_service import AdService
    from app.utils.validators import sanitize_text, ValidationError
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

            # Price handling: prefer the server-computed value so we don't
            # depend on the client-side hidden-input update.
            price_gourdes_raw = (request.form.get('price_gourdes') or '').strip() or '0'
            try:
                price_gourdes = float(price_gourdes_raw) if ad_type == 'sell' else 0.0
            except (ValueError, TypeError):
                price_gourdes = 0.0
            price_gkach_form = (request.form.get('price_gkach') or '').strip() or '0'
            try:
                price_gkach = int(price_gkach_form)
            except (ValueError, TypeError):
                price_gkach = 0
            if ad_type == 'sell' and price_gkach <= 0 and price_gourdes > 0:
                rate = float(current_app.config.get('GKACH_TO_HTG_RATE', 1.2) or 1.2)
                try:
                    price_gkach = int(round(float(price_gourdes) / rate))
                except Exception:
                    price_gkach = 0

            category = sanitize_text(request.form.get('category', '')) or 'other'

            # Quantity (inventory) — only meaningful for ad_type == 'sell'.
            # Enforce server-side: min 1, integer. Fallback 1 if missing/invalid
            # so JS-bypassed submit still produces a valid sell ad (single item).
            quantity_raw = (request.form.get('quantity') or '').strip() or '1'
            try:
                quantity = int(quantity_raw)
            except (ValueError, TypeError):
                quantity = 1
            if ad_type == 'sell' and quantity < 1:
                quantity = 1
            elif ad_type != 'sell':
                quantity = 0

            # Back-end required-field guards (matches the HTML5 `required`).
            if not title or not title.strip():
                raise ValidationError('Tanpri ekri yon tit pou piblisite w la.')
            if not description or not description.strip():
                raise ValidationError('Tanpri ekri yon deskripsyon pou piblisite w la.')
            if ad_type == 'sell' and price_gkach <= 0:
                raise ValidationError('Tanpri mete yon pri val pou piblisite sa a (VANN bezwen pri).')
            if ad_type == 'sell' and (quantity is None or quantity < 1):
                raise ValidationError('Tanpri mete kantite ki disponib (minimòm 1).')
            accept_terms = request.form.get('accept_terms', '')
            if str(accept_terms).lower() not in ('on', 'true', '1', 'yes', 'oui'):
                raise ValidationError(
                    "Ou dwe li epi aksepte Kondisyon ak Règleman anvan ou soumèt."
                )

            # Upload folder: resolve relative to instance dir robustly.
            upload_folder = os.path.join(
                current_app.root_path, '..', current_app.config['UPLOAD_FOLDER']
            )
            upload_folder = os.path.abspath(upload_folder)
            os.makedirs(upload_folder, exist_ok=True)

            images = []
            video = None

            if media_type == 'images':
                for i in range(1, 4):
                    file = request.files.get(f'image_{i}')
                    if file and file.filename:
                        ext = (
                            file.filename.rsplit('.', 1)[-1].lower()
                            if '.' in file.filename else 'jpg'
                        )
                        filename = f'{uuid.uuid4().hex}.{ext}'
                        dest = os.path.join(upload_folder, filename)
                        file.save(dest)
                        images.append(filename)
                if not images:
                    raise ValidationError('Tanpri telechaje omwen yon imaj.')

            elif media_type == 'video':
                file = request.files.get('video')
                if file and file.filename:
                    ext = (
                        file.filename.rsplit('.', 1)[-1].lower()
                        if '.' in file.filename else 'mp4'
                    )
                    filename = f'{uuid.uuid4().hex}.{ext}'
                    file.save(os.path.join(upload_folder, filename))
                    video = filename
                else:
                    raise ValidationError('Tanpri telechaje yon videyo.')

            ad = AdService.create_ad(
                user_whatsapp=whatsapp,
                title=title,
                description=description,
                media_type=media_type,
                images=','.join(images) if images else None,
                video=video,
                ad_type=ad_type,
                price_gkach=price_gkach,
                category=category,
                quantity=quantity
            )
            # Apply fixed publication fee (1000 Gkach) for every new ad so the
            # admin panel + upload_payment page display it.
            try:
                from app import db as _db
                ad.publish_fee_gkach = ADS_PUBLISH_FEE
                _db.session.commit()
            except Exception:
                from app import db as _db2
                _db2.session.rollback()

            flash(
                f'Piblisite soumèt avèk siksè! Ou dwe PEYE {ADS_PUBLISH_FEE} Gkach '
                f'(≈ {round(float(ADS_PUBLISH_FEE) * float(current_app.config.get("GKACH_TO_HTG_RATE",1.2) or 1.2), 2):.2f} HTG) '
                f'pou ADMIN ka aksepte l epi li afiche nan mache a.',
                'success'
            )
            return redirect(url_for('main.upload_payment', ad_id=ad.ad_id))

        except ValidationError as e:
            flash(str(e), 'error')
        except Exception as e:
            current_app.logger.error(f"submit_ad failed: {e}")
            flash('Erè pandan soumèt piblisite a.', 'error')
    
    return render_template('submit_ad.html')


@main_bp.route('/api/posts/preview-url', methods=['POST'])
def preview_url():
    """Preview URL metadata for auto-display"""
    from app.utils.validators import validate_url, ValidationError, sanitize_text
    import requests
    from bs4 import BeautifulSoup
    import re
    
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        
        # Validate and sanitize URL
        url = validate_url(url)
        
        # Check for YouTube URLs
        youtube_regex = r'(?:youtube\.com\/(?:watch\?v=|shorts\/|embed\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})'
        youtube_match = re.search(youtube_regex, url)
        
        if youtube_match:
            video_id = youtube_match.group(1)
            return jsonify({
                'success': True,
                'metadata': {
                    'title': 'YouTube Video',
                    'description': '',
                    'image': f'https://img.youtube.com/vi/{video_id}/maxresdefault.jpg',
                    'site_name': 'YouTube',
                    'url': url,
                    'type': 'youtube',
                    'video_id': video_id,
                    'embed_url': f'https://www.youtube.com/embed/{video_id}?autoplay=1&mute=1'
                }
            })
        
        # Fetch URL content for non-YouTube URLs
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
            'url': url,
            'type': 'link'
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


@main_bp.route('/qr')
def qr_code():
    """QR Code page to scan and launch the app"""
    # Detect the app URL from the request
    host = flask_req.host
    scheme = flask_req.scheme
    app_url = f"{scheme}://{host}"
    return render_template('qr_code.html', app_url=app_url)


@main_bp.route('/demo')
def demo():
    """Demo page with autoplay video"""
    host = flask_req.host
    scheme = flask_req.scheme
    app_url = f"{scheme}://{host}"
    video_url = url_for('static', filename='glory2yahpub_demo.mp4')
    return render_template('demo.html', app_url=app_url, video_url=video_url)
