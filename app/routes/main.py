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


# #region debug-point H:main-index-entry (H1 H2 H3)
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
def _dbg_log(hypothesisId, msg, data=None, runId='post', location='main.py'):
    try:
        import urllib.request as _ur
        payload = {'sessionId': _DBG_S, 'runId': runId, 'hypothesisId': hypothesisId,
                   'location': location, 'msg': '[DEBUG] '+msg,
                   'data': data or {}, 'ts': int(_dbg_time.time()*1000)}
        body = _dbg_json.dumps(payload).encode()
        try:
            _ur.urlopen(_ur.Request(_DBG_U, data=body, headers={'Content-Type':'application/json'}), timeout=1).read()
            return
        except Exception:
            pass
        with _DBG_LOCK:
            _dbg_os.makedirs('.dbg', exist_ok=True)
            with open(_DBG_NDJSON, 'a', encoding='utf-8') as f:
                f.write(_dbg_json.dumps(payload)+'\n')
    except Exception:
        pass
# #endregion

# #region debug-point V:publish-video-not-loading (H1..H5)
_DBG_P_V = '.dbg/publish-video-not-loading.env'
_DBG_U_V, _DBG_S_V = 'http://127.0.0.1:7777/event', 'publish-video-not-loading'
try:
    with open(_DBG_P_V) as _dbg_fv:
        _dbg_cv = _dbg_fv.read()
        for _dbg_lv in _dbg_cv.split('\n'):
            if _dbg_lv.startswith('DEBUG_SERVER_URL='): _DBG_U_V = _dbg_lv.split('=',1)[1].strip()
            elif _dbg_lv.startswith('DEBUG_SESSION_ID='): _DBG_S_V = _dbg_lv.split('=',1)[1].strip()
except Exception:
    pass
_DBG_LOCK_V = _dbg_thr.Lock()
_DBG_NDJSON_V = '.dbg/trae-debug-log-publish-video-not-loading.ndjson'
def _dbg_vlog(hypothesisId, msg, data=None, runId='pre', location='main.py'):
    try:
        import urllib.request as _urv
        payload = {'sessionId': _DBG_S_V, 'runId': runId, 'hypothesisId': hypothesisId,
                   'location': location, 'msg': '[DEBUG] '+msg,
                   'data': data or {}, 'ts': int(_dbg_time.time()*1000)}
        body_v = _dbg_json.dumps(payload).encode()
        try:
            _urv.urlopen(_urv.Request(_DBG_U_V, data=body_v, headers={'Content-Type':'application/json'}), timeout=1).read()
            return
        except Exception:
            pass
        with _DBG_LOCK_V:
            _dbg_os.makedirs('.dbg', exist_ok=True)
            with open(_DBG_NDJSON_V, 'a', encoding='utf-8') as fv:
                fv.write(_dbg_json.dumps(payload)+'\n')
    except Exception:
        pass
# #endregion


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
    # Flush Redis approved-ads cache (prevents stale 'sell-only' cached rows from
    # pre-200eaea builds hiding all approved 'publish' type ads from carousels/feeds)
    try:
        from app.services.redis_service import RedisService
        from app import redis_client as _rc
        _rs = RedisService(_rc)
        _rs.invalidate_approved_ads()
    except Exception:
        pass
    # #region debug-point C:main-cache-flushed (H3)
    _dbg_log('C', 'main.index() cache flushed; starting DB query for ALL approved ads (sell+publish)',
             {'route': '/'}, location='main.py:index:entry')
    # #endregion

    # Robust ad-to-dict helper: NEVER raise on missing columns (legacy SQLite DBs on
    # Render may skip ALTER TABLE migrations for quantity/publish_fee_gkach causing
    # AttributeError → empty feed silently)
    def _safe_ad_to_dict(ad):
        try:
            return ad.to_dict()
        except Exception:
            import re as _re
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
                yt = _re.search(r'(?:youtube\.com\/(?:watch\?v=|shorts\/|embed\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})', url)
                if yt:
                    video_id = yt.group(1)
                    embed_url = f'https://www.youtube.com/embed/{video_id}?autoplay=1&mute=1&playsinline=1&rel=0&enablejsapi=1'
                else:
                    vm = _re.search(r'(?:vimeo\.com\/)([0-9]+)', url)
                    if vm:
                        video_id = vm.group(1)
                        embed_url = f'https://player.vimeo.com/video/{video_id}?autoplay=1&muted=1&playsinline=1'
            images_list = []
            try:
                imgs = _g('images', '') or ''
                if imgs:
                    images_list = [i.strip() for i in str(imgs).split(',') if i and i.strip()]
            except Exception:
                pass
            video_name = _g('video')
            if video_name:
                try:
                    from flask import url_for as _uf
                    video_url = _uf('static', filename='uploads/' + str(video_name))
                except Exception:
                    video_url = '/static/uploads/' + str(video_name)
            else:
                video_url = None
            qty = _g('quantity', None)
            if qty is None:
                qty = 1 if _g('ad_type', 'sell') == 'sell' else 0
            created = None
            try:
                if ad.created_at is not None:
                    created = ad.created_at.isoformat()
            except Exception:
                pass
            return {
                'id': _g('id'),
                'ad_id': _g('ad_id', ''),
                'user_whatsapp': _g('user_whatsapp', ''),
                'title': _g('title', ''),
                'description': _g('description', ''),
                'media_type': _g('media_type', 'images'),
                'images': images_list,
                'video': video_name,
                'video_url': video_url,
                'video_id': video_id,
                'embed_url': embed_url,
                'ad_type': _g('ad_type', 'sell'),
                'price_gkach': _g('price_gkach', 0) or 0,
                'quantity': qty,
                'publish_fee_gkach': _g('publish_fee_gkach', 1000) or 1000,
                'category': _g('category') or 'other',
                'admin_status': _g('admin_status', 'under_review'),
                'payment_status': _g('payment_status', 'pending'),
                'like_count': _g('like_count', 0) or 0,
                'star_count': _g('star_count', 0) or 0,
                'view_count': _g('view_count', 0) or 0,
                'share_count': _g('share_count', 0) or 0,
                'created_at': created,
            }

    try:
        # Get posts for left side (social feed) - wrap safely
        try:
            posts = AdService.get_approved_ads(page=1, per_page=10)
        except Exception as posts_err:
            current_app.logger.warning(f"main.index AdService.get_approved_ads failed fallback DB query: {posts_err}")
            from app.models.ad import Ad as _Ad
            posts_db = _Ad.query.filter_by(admin_status='approved').order_by(_Ad.created_at.desc()).limit(10).all()
            posts = [_safe_ad_to_dict(a) for a in posts_db]

        # Get ALL approved marketplace ads for carousel - ALL approved types (sell + publish)
        # show up in Mache. Approved announcements / services / jobs etc. must be visible.
        from app.models.ad import Ad
        marketplace_ads = Ad.query.filter_by(admin_status='approved').order_by(Ad.created_at.desc()).all()
        marketplace_ads_dict = [_safe_ad_to_dict(ad) for ad in marketplace_ads]

        # #region debug-point V:main-index-video-breakdown (H2 H5)
        try:
            post_video_cnt = sum(1 for p in (posts or []) if (p.get('media_type')=='video' and (p.get('video') or p.get('video_url'))))
            mp_video_cnt = sum(1 for p in (marketplace_ads_dict or []) if (p.get('media_type')=='video' and (p.get('video') or p.get('video_url'))))
            post_missing_video_url = sum(1 for p in (posts or []) if p.get('media_type')=='video' and not p.get('video_url'))
            _dbg_vlog('H2', f'main.index() video ads breakdown: posts video_count={post_video_cnt}; carousel video_count={mp_video_cnt}; posts(mt=video & no video_url)={post_missing_video_url}',
                     {'posts_video_count': post_video_cnt, 'carousel_video_count': mp_video_cnt, 'posts_with_video_missing_url': post_missing_video_url},
                     location='main.py:index:video-breakdown')
        except Exception:
            pass
        # #endregion

        # #region debug-point C:main-index-success-exit (H1 H2 H3)
        from collections import Counter as _Cnt
        posts_types = dict(_Cnt(p.get('ad_type','?') for p in (posts or [])))
        mp_types = dict(_Cnt(p.get('ad_type','?') for p in (marketplace_ads_dict or [])))
        _dbg_log('C', f'main.index() exit success posts.len={len(posts or [])} types={posts_types}; carousel ads.len={len(marketplace_ads_dict)} types={mp_types}',
                 {'posts_len': len(posts or []), 'posts_types': posts_types,
                  'marketplace_ads_len': len(marketplace_ads_dict), 'marketplace_types': mp_types},
                 location='main.py:index:exit-ok')
        # #endregion
        return render_template(
            'index.html',
            posts=posts,
            marketplace_ads=marketplace_ads_dict,
            current_user=current_user
        )
    except Exception as e:
        import traceback as _tb
        current_app.logger.error(f"FATAL main.index exception: {e}\n{_tb.format_exc()}")
        # #region debug-point C:main-index-fatal (H4)
        _dbg_log('C', f'main.index() FATAL exception swallowed',
                 {'exception': str(e), 'stack': _tb.format_exc()[:800]},
                 location='main.py:index:exit-fatal')
        # #endregion
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
        # FIX: SQLAlchemy 2.x rejects raw string SQL — must wrap in text().
        # Before, db.session.execute('SELECT 1') ALWAYS raised ArgumentError, so
        # /health returned 503 "database=False" even when the DB was reachable,
        # making Render's healthCheckPath (/health) permanently "unhealthy".
        from sqlalchemy import text
        from app import db
        db.session.execute(text('SELECT 1'))
        health['database'] = True
    except Exception:
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
            upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
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
                upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
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
@login_required
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
    from app.services.ad_service import AdService
    from app.utils.validators import sanitize_text, validate_url, ValidationError
    import os
    import uuid
    from flask import flash, redirect, url_for
    
    if request.method == 'POST':
        try:

            whatsapp = current_user.whatsapp
            media_type = request.form.get('media_type', 'images')
            ad_type = request.form.get('ad_type', 'publish')
            title = sanitize_text(request.form.get('title', ''))
            description = sanitize_text(request.form.get('description', ''))
            # #region debug-point V:submit_ad entry (H1 H4 H5)
            _dbg_vlog('H1', f'submit_ad POST entry media_type={media_type} ad_type={ad_type}',
                     {'media_type': media_type, 'ad_type': ad_type, 'user_whatsapp': whatsapp,
                      'title_len': len(title), 'desc_len': len(description)},
                     location='main.py:submit_ad:entry')
            # #endregion
            try:
                video_file_in = request.files.get('video') if media_type == 'video' else None
                if video_file_in and video_file_in.filename:
                    video_file_in.seek(0, 2)
                    vsz = video_file_in.tell()
                    video_file_in.seek(0)
                else:
                    vsz = 0
            except Exception:
                vsz = None
            _dbg_vlog('H1', f'submit_ad payload sizes: video_bytes={vsz}',
                     {'video_bytes': vsz}, location='main.py:submit_ad:payload-size')

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

            # Description guard: for media_type='url', description TEXT is optional
            # because the external_url itself is always stored inside description
            # (combined: URL + "\n\n" + text). So the guard only fires if:
            #   - NOT url type AND text description empty  OR
            #   - url type AND no external_url was provided (will be caught in url branch too but keep belt+braces)
            _has_url_fallback = (
                media_type == 'url' and
                bool((request.form.get('external_url') or '').strip())
            )
            if (not description or not description.strip()) and not _has_url_fallback:
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

            # Upload folders: resolve robustly.
            #
            # THREE-LAYER PERSISTENCE (belt + suspenders + harness),
            # **ULTRA-FAST + ULTRA-GRACEFUL**:
            #   1. STAGING_UPLOAD_FOLDER → raw bytes land here FIRST
            #   2. UPLOAD_FOLDER (FINAL) → moved here AFTER checks (what PostgreSQL stores)
            #   3. BACKUP_UPLOAD_FOLDER → shutil.copy2 mirror (background thread for big files)
            #
            # PERFORMANCE FIX vs earlier version:
            #   - MD5 is computed INLINE WHILE writing staging bytes
            #     (NO SECOND FULL RE-READ OF 21MB+ VIDEOS on slow Render disk)
            #   - Paths: DON'T re-join with root_path/.. when config path IS ALREADY ABSOLUTE
            #     (that double-join was harmless but wasteful + wrong for Windows abs paths)
            #   - Backup on files > 5 MB: runs in a background daemon thread so the
            #     HTTP response does NOT wait on a second 21MB copy on slow Render disk
            #     (this alone was a primary cause of Render 30s → ERR_CONNECTION_ABORTED).
            #   - **FALLBACK CHAIN**: ANY exception in staging/backup layers →
            #     we fall back to the DIRECT classic file.save(UPLOAD_FOLDER) path.
            #     We NEVER let persistence infra crash a user upload.

            def _resolve_upload_dir(key_env, fallback_rel):
                raw = current_app.config.get(key_env)
                if raw and os.path.isabs(raw):
                    return os.path.abspath(raw)
                # env-var overridden explicitly, or relative path — resolve vs project root
                candidate = raw or fallback_rel
                if os.path.isabs(candidate):
                    return os.path.abspath(candidate)
                return os.path.abspath(os.path.join(current_app.root_path, '..', candidate))

            upload_folder = _resolve_upload_dir('UPLOAD_FOLDER', os.path.join('static', 'uploads'))
            staging_folder = _resolve_upload_dir('STAGING_UPLOAD_FOLDER', os.path.join('instance', 'uploads_staging'))
            backup_folder = _resolve_upload_dir('BACKUP_UPLOAD_FOLDER', os.path.join('instance', 'uploads_backup'))
            try:
                os.makedirs(upload_folder, exist_ok=True)
            except Exception:
                pass
            try:
                os.makedirs(staging_folder, exist_ok=True)
            except Exception:
                staging_folder = upload_folder  # graceful fallback
            try:
                os.makedirs(backup_folder, exist_ok=True)
            except Exception:
                backup_folder = None  # backup is optional

            import threading as _thr

            def _bg_backup_copy(src_path, dst_path):
                """Daemon-thread backup so Render HTTP 30s timeout is not hit."""
                try:
                    import shutil as _shutil_bg
                    _shutil_bg.copy2(src_path, dst_path)
                except Exception:
                    pass  # backup is best-effort

            def _stage_and_persist_upload(file_storage, ext_expected, label='file'):
                """Stage file, inline MD5 while saving, move → final, backup in bg if large.

                **Guaranteed to never raise a non-ValidationError that would crash the upload**.
                On ANY I/O / disk failure → falls back to the classic direct save into
                upload_folder (the pre-persistence behaviour)."""
                import shutil as _shutil
                import hashlib as _hashlib
                if not file_storage or not file_storage.filename:
                    raise ValidationError(f'Fichye {label} a manke.')

                final_name = f'{uuid.uuid4().hex}.{ext_expected.lower()}'
                final_path = os.path.join(upload_folder, final_name)

                # ============ FAST PATH 1) — stream + inline MD5 = 1 pass over the bytes ============
                try:
                    stage_path = os.path.join(staging_folder, final_name)
                    _h = _hashlib.md5()
                    _total_written = 0
                    try:
                        file_storage.seek(0)
                    except Exception:
                        pass
                    with open(stage_path, 'wb') as _sfh:
                        while True:
                            _chunk = file_storage.read(1024 * 1024)  # 1 MB chunks, streamed
                            if not _chunk:
                                break
                            _sfh.write(_chunk)
                            _h.update(_chunk)
                            _total_written += len(_chunk)
                    _md5_digest = _h.hexdigest()
                    stage_bytes = _total_written

                    if stage_bytes <= 0:
                        try:
                            os.unlink(stage_path)
                        except Exception:
                            pass
                        raise ValidationError(f'Fichye {label} a vid. Tanpri chwazi yon lòt.')
                    if not _md5_digest:
                        try:
                            os.unlink(stage_path)
                        except Exception:
                            pass
                        raise ValidationError(
                            f'Pa ka kalkile MD5 fichye {label} a — done yo kòronp.'
                        )

                    # ============ 2) move staging → final (atomic on same FS / disk Render) ============
                    try:
                        _shutil.move(stage_path, final_path)
                    except Exception as _e_move:
                        try:
                            if (
                                os.path.exists(stage_path)
                                and os.path.abspath(stage_path) != os.path.abspath(final_path)
                            ):
                                try:
                                    _shutil.copy2(stage_path, final_path)
                                    try:
                                        os.unlink(stage_path)
                                    except Exception:
                                        pass
                                except Exception:
                                    pass
                        except Exception:
                            pass
                        if not os.path.exists(final_path):
                            raise ValidationError(
                                f'Pa ka deplase fichye {label} a nan dosye final. Eseye ankò.'
                                f' ({_e_move!r})'
                            )

                    # ============ 3) Backup mirror — bg thread for > 5 MB, else inline ============
                    if backup_folder and os.path.exists(final_path):
                        try:
                            backup_path = os.path.join(backup_folder, final_name)
                            if stage_bytes > 5 * 1024 * 1024:
                                # Large files (videos): don't block the HTTP response.
                                # This single change fixes the Render 30s → ERR_CONNECTION_ABORTED.
                                try:
                                    t = _thr.Thread(
                                        target=_bg_backup_copy,
                                        args=(final_path, backup_path),
                                        daemon=True,
                                    )
                                    t.start()
                                except Exception:
                                    # Thread spawn failed (unusual): best effort, try inline tiny.
                                    try:
                                        _shutil.copy2(final_path, backup_path)
                                    except Exception:
                                        pass
                            else:
                                # Small images: inline copy is fine (<<1s).
                                try:
                                    _shutil.copy2(final_path, backup_path)
                                except Exception:
                                    pass
                        except Exception:
                            pass  # backup is belt+suspenders, never a hard failure

                    _dbg_vlog('H1', f'upload persist-3l ok — {label}={final_name} bytes={stage_bytes}',
                             {'filename': final_name, 'label': label,
                              'bytes': stage_bytes, 'md5_prefix': _md5_digest[:8],
                              'final_exists': os.path.exists(final_path)},
                             location='main.py:submit_ad:stage_and_persist')
                    return final_name
                except ValidationError:
                    raise  # re-raise explicit user-facing validation errors cleanly
                except Exception as _e_fallback:
                    # ============= FALLBACK CHAIN — any persistence/permission error → OLD DIRECT SAVE =============
                    try:
                        try:
                            file_storage.seek(0)
                        except Exception:
                            pass
                        file_storage.save(final_path)
                        if os.path.exists(final_path) and os.path.getsize(final_path) > 0:
                            _dbg_vlog('H1',
                                     f'upload FALLBACK ok (staging failed {_e_fallback!r}) — {label}={final_name}',
                                     {'filename': final_name, 'label': label,
                                      'bytes': os.path.getsize(final_path),
                                      'fallback_reason': str(_e_fallback)[:80]},
                                     location='main.py:submit_ad:stage_and_persist:fallback')
                            return final_name
                    except Exception as _e_last:
                        pass
                    # Could not save even via direct path: hard error
                    raise ValidationError(
                        f'Pa ka sovegade fichye {label} a. Eseye ankò oswa eseye yon fichye ki pi piti.'
                        f' ({_e_fallback!r})'
                    )

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
                        filename = _stage_and_persist_upload(file, ext, label=f'imaj{i}')
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
                    allowed_video_ext = current_app.config.get('ALLOWED_VIDEO_EXTENSIONS', {'mp4','avi','mov','mkv','webm'})
                    if ext not in allowed_video_ext:
                        raise ValidationError(
                            f'Tip videyo a pa aksepte. Aksepte sèlman: {", ".join(sorted(allowed_video_ext)).upper()}.'
                        )
                    # Video size pre-check: use the already-buffered werkzeug stream length if available.
                    _video_pre_bytes = None
                    try:
                        file.seek(0, 2)
                        _video_pre_bytes = file.tell()
                        file.seek(0)
                    except Exception:
                        _video_pre_bytes = None
                    if _video_pre_bytes is not None:
                        max_bytes = int(current_app.config.get('MAX_CONTENT_LENGTH', 100*1024*1024))
                        if _video_pre_bytes > max_bytes:
                            raise ValidationError(
                                f'Videyo a twò gwo (≈{round(_video_pre_bytes/1024/1024,1)} MB).'
                                f' Maksimòm otorize: {max_bytes//1024//1024} MB.'
                            )
                    filename = _stage_and_persist_upload(file, ext, label='videyo')
                    video = filename
                    _dbg_vlog('H1', f'video upload saved: {filename} ext={ext}',
                             {'filename': filename, 'ext': ext,
                              'dest_exists': os.path.exists(os.path.join(upload_folder, filename))},
                             location='main.py:submit_ad:video-saved')
                else:
                    raise ValidationError('Tanpri telechaje yon videyo.')

            elif media_type == 'url':
                external_url_raw = (request.form.get('external_url') or '').strip()
                if not external_url_raw:
                    raise ValidationError(
                        'Tanpri kole lien videyo a (YouTube, TikTok, Vimeo, Facebook, Instagram Reels).'
                    )
                try:
                    external_url_validated = validate_url(external_url_raw)
                except ValidationError:
                    raise ValidationError(
                        'Lien videyo a pa valab. Li dwe kòmanse ak https:// oswa http:// '
                        '(egzanp: https://youtube.com/watch?v=XYZ).'
                    )
                combined_description = external_url_validated
                if description and description.strip() and description.strip().lower() != external_url_validated.lower():
                    combined_description = external_url_validated + "\n\n" + description.strip()
                description = combined_description
                _dbg_vlog('H1', f'URL media validated ok len_url={len(external_url_validated)}',
                         {'external_url': external_url_validated,
                          'desc_len': len(description or ''),
                          'platforms_detected': [
                              p for p, has in (
                                  ('youtube', 'youtube' in external_url_validated.lower() or 'youtu.be' in external_url_validated.lower()),
                                  ('vimeo', 'vimeo' in external_url_validated.lower()),
                                  ('tiktok', 'tiktok' in external_url_validated.lower()),
                                  ('instagram', 'instagram' in external_url_validated.lower() or 'instagr.am' in external_url_validated.lower()),
                                  ('facebook', 'facebook' in external_url_validated.lower() or 'fb.watch' in external_url_validated.lower()),
                              ) if has
                          ]},
                         location='main.py:submit_ad:url-media-ok')

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
            _dbg_vlog('H1', f'create_ad SUCCESS ad_id={ad.ad_id} video={bool(video)} images_cnt={len(images)}',
                     {'ad_id': getattr(ad, 'ad_id', None), 'media_type': media_type,
                      'ad_type': ad_type, 'video': video, 'images_cnt': len(images),
                      'publish_fee_gkach': getattr(ad, 'publish_fee_gkach', None)},
                     location='main.py:submit_ad:create_ad-success')
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
            _dbg_vlog('H5', f'submit_ad ValidationError: {str(e)}',
                     {'error': str(e), 'media_type': request.form.get('media_type','?')},
                     location='main.py:submit_ad:validation-error')
            flash(str(e), 'error')
        except Exception as e:
            import traceback as _tb2
            _dbg_vlog('H1', f'submit_ad FATAL exception {type(e).__name__}: {str(e)}',
                     {'error': str(e), 'traceback': _tb2.format_exc()[:1200]},
                     location='main.py:submit_ad:fatal-exception')
            current_app.logger.error(f"submit_ad failed: {e}\n{_tb2.format_exc()}")
            if isinstance(e, OverflowError) or ('Maximum ' in str(e) and 'content length' in str(e).lower()) or 'RequestEntityTooLarge' in type(e).__name__:
                flash('Fichye a twò gwo. Maksimòm otorize: 100MB pou videyo. Tanpri chwazi yon pi piti.', 'error')
            else:
                flash('Erè pandan soumèt piblisite a.', 'error')
    
    return render_template('submit_ad.html')


@main_bp.route('/api/posts/preview-url', methods=['GET'])
def preview_url():
    """Preview URL metadata for auto-display (GET + query param = no CSRF / idempotent).
    YouTube shortcut: returns metadata instantly without external fetch.
    """
    from app.utils.validators import validate_url, ValidationError, sanitize_text
    import requests
    from bs4 import BeautifulSoup
    import re

    try:
        url = request.args.get('url', '').strip()

        # Validate and sanitize URL
        url = validate_url(url)

        # Check for YouTube URLs (short-circuit: no external HTTP needed)
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
                    'embed_url': f'https://www.youtube.com/embed/{video_id}?autoplay=1&mute=1&playsinline=1&rel=0&enablejsapi=1&modestbranding=1'
                }
            })

        # Fetch URL content for non-YouTube URLs
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        response = requests.get(url, headers=headers, timeout=8)
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
        return jsonify({'success': False, 'message': 'Pa ka aksede URL la (verifye koneksyon ou).'}), 400
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
