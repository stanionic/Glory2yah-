from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, make_response, send_from_directory
from models import db, Ad, Batch, UserGkach, GkachRate, Delivery, Message
import uuid
import os
import json
import random
import csv
from datetime import datetime
from werkzeug.utils import secure_filename
from src.logger import setup_logger
from moviepy.editor import VideoFileClip
from PIL import Image
from image_search import find_similar_ads
from src.notifications import (
    notify_admin_new_gkach_request,
    notify_admin_balance_change,
    notify_admin_request_approved,
    notify_admin_request_rejected,
    notify_admin_new_ad_submission,
    notify_admin_payment_proof_uploaded,
    notify_user_ad_approved,
    notify_user_ad_rejected,
    notify_admin_ad_purchased,
    notify_user_ad_purchased,
    notify_admin_gkach_approval_uploaded,
    notify_user_gkach_request_approved,
    notify_user_gkach_request_rejected,
    notify_user_balance_added,
    notify_admin_traffic_alert,
    notify_admin_otp,
    notify_seller_delivery_request,
    notify_buyer_delivery_updated,
    notify_buyer_cart_submitted
)
from src.communication import send_message, get_messages, get_delivery_participants

app = Flask(__name__)
app.secret_key = 'glory2yahpub_secret_key_2024'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB for video uploads
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///glory2yahpub.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# Set up logger
logger = setup_logger()

# Traffic tracking
traffic_log = []

# Custom Jinja2 filter for fromjson
def fromjson(value):
    return json.loads(value)

app.jinja_env.filters['fromjson'] = fromjson

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def generate_otp():
    """Generate a 4-digit random OTP"""
    return str(random.randint(1000, 9999))

with app.app_context():
    db.create_all()
    # Add missing columns if not exists
    from sqlalchemy import text
    try:
        db.session.execute(text("ALTER TABLE ads ADD COLUMN media_type VARCHAR(10) DEFAULT 'images'"))
        db.session.commit()
    except:
        pass  # Column already exists
    try:
        db.session.execute(text("ALTER TABLE ads ADD COLUMN video VARCHAR(255)"))
        db.session.commit()
    except:
        pass  # Column already exists

@app.before_request
def log_traffic():
    if request.endpoint not in ['static']:
        traffic_entry = {
            'timestamp': datetime.now().isoformat(),
            'ip': request.remote_addr,
            'method': request.method,
            'path': request.path,
            'user_agent': request.headers.get('User-Agent', ''),
            'referrer': request.headers.get('Referer', '')
        }
        traffic_log.append(traffic_entry)
        # Keep only last 1000 entries
        if len(traffic_log) > 1000:
            traffic_log.pop(0)

        # Notify admin if traffic exceeds threshold
        if len(traffic_log) > 10:  # Example threshold
            notify_admin_traffic_alert(len(traffic_log))

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password')

        if password == 'StanGlory2YahPub0886':  # Hardcoded for now
            session['admin'] = True
            flash('Konekte kòm administratè avèk siksè.', 'success')
            return redirect(url_for('admin'))
        else:
            flash('Modpas envalid.', 'error')
    return render_template('admin_login.html')

@app.route('/')
def index():
    # Fetch the latest batch
    latest_batch = Batch.query.order_by(Batch.created_at.desc()).first()
    batch = None
    ads = []
    if latest_batch:
        batch = latest_batch
        ad_ids = batch.ads.split(',')
        ads = Ad.query.filter(Ad.ad_id.in_(ad_ids)).all()
    response = make_response(render_template('index.html', batch=batch, ads=ads))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/welcome', methods=['GET'])
def welcome():
    """
    Returns a welcome message
    """
    logger.info(f"Request received: {request.method} {request.path}")
    return jsonify({'message': 'Welcome to the Glory2yahPub API Service!'})

@app.route('/submit_ad', methods=['GET', 'POST'])
def submit_ad():
    if request.method == 'POST':
        logger.info("Submit ad POST received")
        logger.info(f"Form data: whatsapp={request.form.get('whatsapp')}, description={request.form.get('description')}")
        logger.info(f"Files received: {list(request.files.keys())}")
        user_whatsapp = request.form.get('whatsapp', '').strip()
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        price_gkach = request.form.get('price_gkach', '').strip()

        # Format WhatsApp number: remove non-digits, ensure +509 prefix
        user_whatsapp = ''.join(filter(str.isdigit, user_whatsapp))
        if not user_whatsapp.startswith('509'):
            user_whatsapp = '509' + user_whatsapp
        user_whatsapp = '+' + user_whatsapp

        if not user_whatsapp or len(user_whatsapp) < 12:  # Basic validation for +509xxxxxxxx
            flash('Numéro WhatsApp valab obligatwa (egz: +50912345678).', 'error')
            return redirect(url_for('submit_ad'))
        if not title:
            flash('Tit piblisite a obligatwa.', 'error')
            return redirect(url_for('submit_ad'))
        if not description:
            flash('Deskripsyon piblisite a obligatwa.', 'error')
            return redirect(url_for('submit_ad'))
        try:
            price_gkach = int(price_gkach)
            if price_gkach <= 0:
                raise ValueError
        except ValueError:
            flash('Pri Gkach valab obligatwa (egz: 100).', 'error')
            return redirect(url_for('submit_ad'))

        # Check terms acceptance
        if not request.form.get('accept_terms'):
            flash('Ou dwe aksepte kondisyon ak règleman yo pou soumèt piblisite.', 'error')
            return redirect(url_for('submit_ad'))

        media_type = request.form.get('media_type', 'images')
        images = []
        video = None

        if media_type == 'images':
            for i in range(1, 4):
                image_field = f'image_{i}'
                if image_field in request.files:
                    file = request.files[image_field]
                    logger.info(f"Processing file {image_field}: filename={file.filename}, content_type={file.content_type}")
                    if file and allowed_file(file.filename):
                        images.append(file)
                    else:
                        logger.warning(f"File {image_field} not allowed: {file.filename}")

            logger.info(f"Total valid images: {len(images)}")
            if len(images) != 3:
                logger.error(f"Expected 3 images, got {len(images)}")
                flash('Ou dwe upload egzakteman 3 imaj pou piblisite w la.', 'error')
                return redirect(url_for('submit_ad'))
        elif media_type == 'video':
            if 'video' in request.files:
                file = request.files['video']
                logger.info(f"Processing video file: filename={file.filename}, content_type={file.content_type}")
                if file and file.filename and file.filename.rsplit('.', 1)[1].lower() in ['mp4', 'avi', 'mov', 'mkv']:
                    video = file
                else:
                    logger.warning(f"Video file not allowed: {file.filename}")
                    flash('Tip videyo pa aksepte. Sèlman MP4, AVI, MOV, oubyen MKV.', 'error')
                    return redirect(url_for('submit_ad'))
            else:
                flash('Ou dwe upload yon videyo pou piblisite w la.', 'error')
                return redirect(url_for('submit_ad'))

        # Ensure upload directory exists
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

        # Now save files
        saved_images = []
        saved_video = None

        if media_type == 'images':
            for file in images:
                filename = f"{uuid.uuid4()}_{secure_filename(file.filename)}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                try:
                    file.save(filepath)
                    # Compress the image
                    try:
                        img = Image.open(filepath)
                        if img.format in ['JPEG', 'JPG']:
                            img.save(filepath, 'JPEG', quality=80, optimize=True)
                        elif img.format == 'PNG':
                            img.save(filepath, 'PNG', optimize=True)
                        # GIF and others left uncompressed
                        img.close()
                        logger.info(f"Image compressed successfully: {filename}")
                    except Exception as compress_e:
                        logger.warning(f"Error compressing image {filename}: {str(compress_e)}")
                        # Continue without compression
                    saved_images.append(filename)
                    logger.info(f"File saved successfully: {filename}")
                except Exception as e:
                    logger.error(f"Error saving file {filename}: {str(e)}")
                    flash('Erè nan telechajman imaj yo. Eseye ankò.', 'error')
                    return redirect(url_for('submit_ad'))
        elif media_type == 'video':
            filename = f"{uuid.uuid4()}_{secure_filename(video.filename)}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            try:
                video.save(filepath)
                saved_video = filename
                logger.info(f"Video saved successfully: {filename}")
            except Exception as e:
                logger.error(f"Error saving video {filename}: {str(e)}")
                flash('Erè nan telechajman videyo a. Eseye ankò.', 'error')
                return redirect(url_for('submit_ad'))

        ad_id = str(uuid.uuid4())
        created_at = datetime.now().isoformat()

        try:
            new_ad = Ad(
                ad_id=ad_id,
                user_whatsapp=user_whatsapp,
                media_type=media_type,
                images=','.join(saved_images) if saved_images else '',
                video=saved_video,
                description=description,
                title=title,
                price_gkach=price_gkach,
                created_at=datetime.utcnow()
            )
            db.session.add(new_ad)
            db.session.commit()
            logger.info(f"Ad submitted successfully: {ad_id}")
            # Notify admin of new ad submission
            notify_admin_new_ad_submission(user_whatsapp, ad_id)
            flash('Piblisite w la soumèt avèk siksè! Kounye a, telechaje prèv pèman w la.', 'success')
            return redirect(url_for('upload_payment', ad_id=ad_id))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error submitting ad: {str(e)}")
            flash('Erè nan soumisyon piblisite a. Eseye ankò.', 'error')
            return redirect(url_for('submit_ad'))

    return render_template('submit_ad.html')

@app.route('/upload_payment/<ad_id>', methods=['GET', 'POST'])
def upload_payment(ad_id):
    if request.method == 'POST':
        logger.info(f"Upload payment POST for ad_id: {ad_id}")

        # Check terms acceptance
        if not request.form.get('accept_terms'):
            flash('Ou dwe aksepte kondisyon ak règleman yo pou telechaje prèv pèman.', 'error')
            return redirect(url_for('upload_payment', ad_id=ad_id))

        if 'payment_proof' not in request.files:
            logger.warning("No payment_proof file in request")
            flash('Pa gen dosye chwazi.', 'error')
            return redirect(url_for('upload_payment', ad_id=ad_id))

        file = request.files['payment_proof']
        logger.info(f"Payment proof file: {file.filename}, content_type: {file.content_type}")
        if file and allowed_file(file.filename):
            filename = f"payment_{uuid.uuid4()}_{secure_filename(file.filename)}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            try:
                file.save(filepath)
                logger.info(f"Payment proof saved: {filename}")
            except Exception as e:
                logger.error(f"Error saving payment proof: {str(e)}")
                flash('Erè nan telechajman prèv pèman an. Eseye ankò.', 'error')
                return redirect(url_for('upload_payment', ad_id=ad_id))

            try:
                ad = Ad.query.filter_by(ad_id=ad_id).first()
                if ad:
                    ad.payment_proof = filename
                    ad.payment_status = 'pending'
                    db.session.commit()
                    logger.info(f"Payment proof updated for ad: {ad_id}")
                    # Notify admin of payment proof upload
                    notify_admin_payment_proof_uploaded(ad.user_whatsapp, ad_id)
                    flash('Prèv pèman w la telechaje avèk siksè! Administratè a pral revize li byento.', 'success')
                    return redirect(url_for('success'))
                else:
                    logger.error(f"Ad not found: {ad_id}")
                    flash('Piblisite pa jwenn.', 'error')
                    return redirect(url_for('upload_payment', ad_id=ad_id))
            except Exception as e:
                db.session.rollback()
                logger.error(f"Error updating payment proof in DB: {str(e)}")
                flash('Erè nan telechajman prèv pèman an. Eseye ankò.', 'error')
                return redirect(url_for('upload_payment', ad_id=ad_id))
        else:
            logger.warning(f"Payment proof file not allowed: {file.filename}")
            flash('Tip dosye pa aksepte. Sèlman imaj oubyen PDF.', 'error')
            return redirect(url_for('upload_payment', ad_id=ad_id))

    return render_template('upload_payment.html', ad_id=ad_id)

@app.route('/upload_gkach_approval/<request_id>', methods=['GET', 'POST'])
def upload_gkach_approval(request_id):
    if request.method == 'POST':
        logger.info(f"Upload Gkach approval POST for request_id: {request_id}")

        # Check terms acceptance
        if not request.form.get('accept_terms'):
            flash('Ou dwe aksepte kondisyon ak règleman yo pou telechaje dokiman apwobasyon.', 'error')
            return redirect(url_for('upload_gkach_approval', request_id=request_id))

        if 'approval_document' not in request.files:
            logger.warning("No approval_document file in request")
            flash('Pa gen dosye chwazi.', 'error')
            return redirect(url_for('upload_gkach_approval', request_id=request_id))

        file = request.files['approval_document']
        logger.info(f"Approval document file: {file.filename}, content_type: {file.content_type}")
        if file and allowed_file(file.filename):
            filename = f"gkach_approval_{uuid.uuid4()}_{secure_filename(file.filename)}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            try:
                file.save(filepath)
                logger.info(f"Gkach approval document saved: {filename}")
            except Exception as e:
                logger.error(f"Error saving Gkach approval document: {str(e)}")
                flash('Erè nan telechajman dokiman apwobasyon an. Eseye ankò.', 'error')
                return redirect(url_for('upload_gkach_approval', request_id=request_id))

            try:
                # Find the user and update the specific request
                users_gkach = UserGkach.query.all()
                for user_gkach in users_gkach:
                    requests = json.loads(user_gkach.gkach_requests or '[]')
                    for req in requests:
                        if req.get('request_id') == request_id and req['status'] == 'pending':
                            req['document'] = filename
                            user_gkach.gkach_requests = json.dumps(requests)
                            db.session.commit()
                            logger.info(f"Gkach approval document updated for request: {request_id}")
                            flash('Dokiman apwobasyon w la telechaje avèk siksè! Administratè a pral revize li byento.', 'success')
                            return redirect(url_for('success'))
                logger.error(f"Gkach request not found: {request_id}")
                flash('Demann Gkach pa jwenn.', 'error')
                return redirect(url_for('upload_gkach_approval', request_id=request_id))
            except Exception as e:
                db.session.rollback()
                logger.error(f"Error updating Gkach approval document in DB: {str(e)}")
                flash('Erè nan telechajman dokiman apwobasyon an. Eseye ankò.', 'error')
                return redirect(url_for('upload_gkach_approval', request_id=request_id))
        else:
            logger.warning(f"Approval document file not allowed: {file.filename}")
            flash('Tip dokiman pa aksepte. Sèlman imaj oubyen PDF.', 'error')
            return redirect(url_for('upload_gkach_approval', request_id=request_id))

    return render_template('upload_gkach_approval.html', request_id=request_id)

@app.route('/success')
def success():
    return render_template('success.html')

@app.route('/admin')
def admin():
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    try:
        ads = Ad.query.order_by(Ad.created_at.desc()).all()
        batches = Batch.query.order_by(Batch.created_at.desc()).all()
        users_gkach = UserGkach.query.all()
        gkach_rates = GkachRate.query.all()
    except Exception as e:
        logger.error(f"Error fetching admin data: {str(e)}")
        ads = []
        batches = []
        users_gkach = []
        gkach_rates = []

    return render_template('admin.html', ads=ads, batches=batches, users_gkach=users_gkach, gkach_rates=gkach_rates)

@app.route('/admin/csv/<ad_id>')
def download_csv(ad_id):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    csv_path = f'csv/{ad_id}.csv'
    if os.path.exists(csv_path):
        return send_from_directory('csv', f'{ad_id}.csv', as_attachment=True)
    else:
        flash('CSV pa jwenn.', 'error')
        return redirect(url_for('admin'))

@app.route('/admin/update_ad_status', methods=['POST'])
def update_ad_status():
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    ad_id = request.form['ad_id']
    status = request.form['status']
    payment_status = request.form.get('payment_status', 'pending')

    try:
        ad = Ad.query.filter_by(ad_id=ad_id).first()
        if ad:
            ad.admin_status = status
            ad.payment_status = payment_status
            db.session.commit()
            # Notify user based on status
            if status == 'approved':
                notify_user_ad_approved(ad.user_whatsapp, ad_id)
            elif status == 'rejected':
                notify_user_ad_rejected(ad.user_whatsapp, ad_id)
            flash('Estati piblisite a mete ajou avèk siksè!', 'success')
        else:
            flash('Piblisite pa jwenn.', 'error')
    except Exception as e:
        db.session.rollback()
        flash('Erè nan mete ajou estati a.', 'error')

    return redirect(url_for('admin'))

@app.route('/admin/create_batch', methods=['POST'])
def create_batch():
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    try:
        available_ads = Ad.query.filter_by(admin_status='approved', batch_id=None).all()

        if len(available_ads) < 5:
            flash(f'Pa ase piblisite apwouve. Bezwen 5, gen {len(available_ads)} disponib.', 'error')
            return redirect(url_for('admin'))

        # Take up to 5 ads
        selected_ads = available_ads[:5]
        batch_id = str(uuid.uuid4())
        ad_ids = [ad.ad_id for ad in selected_ads]

        # Generate Open Graph data for carousel
        og_data = {
            'title': 'Glory2yahPub Ad Batch',
            'description': 'Check out these amazing ads from Glory2yahPub!',
            'url': url_for('view_batch', batch_id=batch_id, _external=True),
            'images': []
        }
        for ad in selected_ads:
            first_image = ad.images.split(',')[0]
            image_url = url_for('static', filename='uploads/' + first_image, _external=True)
            og_data['images'].append(image_url)
        og_json = json.dumps(og_data)

        new_batch = Batch(
            batch_id=batch_id,
            ads=','.join(ad_ids),
            open_graph_data=og_json,
            created_at=datetime.utcnow()
        )
        db.session.add(new_batch)

        for ad in selected_ads:
            ad.batch_id = batch_id

        db.session.commit()

        flash(f'Nouvo gwoup {batch_id} kreye avèk siksè!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Erè nan kreasyon gwoup la.', 'error')

    return redirect(url_for('admin'))

@app.route('/batch/<batch_id>')
def view_batch(batch_id):
    batch = Batch.query.filter_by(batch_id=batch_id).first()

    if not batch:
        flash('Gwoup sa pa egziste.', 'error')
        return redirect(url_for('index'))

    ad_ids = batch.ads.split(',')
    ads = Ad.query.filter(Ad.ad_id.in_(ad_ids)).all()

    response = make_response(render_template('batch.html', batch=batch, ads=ads))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/achte')
def achte():
    # Get search query from URL parameters
    search_query = request.args.get('search', '').strip()

    # Fetch all approved ads
    approved_ads = Ad.query.filter_by(admin_status='approved').order_by(Ad.created_at.desc()).all()

    # Filter ads based on search query
    if search_query:
        if search_query.startswith('image_search:'):
            # Handle image search results
            ad_ids_str = search_query.replace('image_search:', '')
            ad_ids = ad_ids_str.split(',') if ad_ids_str else []
            approved_ads = [ad for ad in approved_ads if ad.ad_id in ad_ids]
        else:
            # Regular text search
            filtered_ads = []
            for ad in approved_ads:
                title = ad.title or ""
                description = ad.description or ""
                if (search_query.lower() in title.lower() or
                    search_query.lower() in description.lower()):
                    filtered_ads.append(ad)
            approved_ads = filtered_ads

    return render_template('achte.html', ads=approved_ads, search_query=search_query)

@app.route('/search_by_image', methods=['POST'])
def search_by_image():
    if 'image' not in request.files:
        return jsonify({'success': False, 'message': 'Pa gen imaj chwazi.'}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'Pa gen imaj chwazi.'}), 400

    if file and allowed_file(file.filename):
        # Save the uploaded image temporarily
        filename = f"search_{uuid.uuid4()}_{secure_filename(file.filename)}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        try:
            # Perform image search
            similar_ads = find_similar_ads(filepath)

            # Clean up the temporary file
            os.remove(filepath)

            # Return the ad IDs of similar ads
            ad_ids = [ad.ad_id for ad in similar_ads]
            return jsonify({'success': True, 'ad_ids': ad_ids})
        except Exception as e:
            # Clean up the temporary file in case of error
            if os.path.exists(filepath):
                os.remove(filepath)
            logger.error(f"Error in image search: {str(e)}")
            return jsonify({'success': False, 'message': 'Erè nan rechèch pa imaj.'}), 500
    else:
        return jsonify({'success': False, 'message': 'Tip dosye pa aksepte.'}), 400

@app.route('/shopping_cart/<ad_id>', methods=['GET', 'POST'])
def shopping_cart(ad_id):
    ad = Ad.query.filter_by(ad_id=ad_id, admin_status='approved').first()
    if not ad:
        flash('Piblisite pa jwenn.', 'error')
        return redirect(url_for('achte'))

    # Get cart from session or initialize empty cart
    cart = session.get('cart', {})

    if request.method == 'POST':
        action = request.form.get('action', 'add_to_cart')

        if action == 'add_to_cart':
            # Add item to cart
            if ad_id not in cart:
                cart[ad_id] = {
                    'quantity': 1,
                    'price': ad.price_gkach,
                    'title': ad.title,
                    'seller_whatsapp': ad.user_whatsapp
                }
            else:
                cart[ad_id]['quantity'] += 1

            session['cart'] = cart
            flash('Piblisite ajoute nan panier!', 'success')
            return redirect(url_for('achte'))

        elif action == 'checkout':
            user_whatsapp = request.form.get('whatsapp', '').strip()
            delivery_address = request.form.get('delivery_address', '').strip()

            # Format WhatsApp number: ensure +509xxxxxxxx format
            user_whatsapp_digits = ''.join(filter(str.isdigit, user_whatsapp))
            if len(user_whatsapp_digits) >= 8:
                user_whatsapp = '+509' + user_whatsapp_digits[-8:]
            else:
                user_whatsapp = ''

            if not user_whatsapp:
                flash('Numéro WhatsApp valab obligatwa (eg: +50912345678).', 'error')
                return redirect(url_for('shopping_cart', ad_id=ad_id))
            if not delivery_address:
                flash('Adrès livrezon obligatwa.', 'error')
                return redirect(url_for('shopping_cart', ad_id=ad_id))
            if not cart:
                flash('Panier ou vid.', 'error')
                return redirect(url_for('shopping_cart', ad_id=ad_id))

            # Check terms acceptance
            if not request.form.get('accept_terms'):
                flash('Ou dwe aksepte kondisyon ak règleman yo pou achte piblisite.', 'error')
                return redirect(url_for('shopping_cart', ad_id=ad_id))

            # Group cart items by seller
            seller_carts = {}
            for item_ad_id, item_data in cart.items():
                seller = item_data['seller_whatsapp']
                if seller not in seller_carts:
                    seller_carts[seller] = []
                seller_carts[seller].append({
                    'ad_id': item_ad_id,
                    'quantity': item_data['quantity'],
                    'price': item_data['price'],
                    'title': item_data['title']
                })

            # Create delivery records for each seller
            delivery_ids = []
            for seller_whatsapp, items in seller_carts.items():
                delivery_id = str(uuid.uuid4())
                total_price = sum(item['price'] * item['quantity'] for item in items)

                delivery = Delivery(
                    delivery_id=delivery_id,
                    buyer_whatsapp=user_whatsapp,
                    seller_whatsapp=seller_whatsapp,
                    delivery_cost=0,  # To be set by seller
                    total_price=total_price,
                    status='negotiating',
                    cart_items=json.dumps(items),
                    delivery_address=delivery_address
                )
                db.session.add(delivery)
                delivery_ids.append(delivery_id)

                # Send WhatsApp notification to seller with cart details
                notify_seller_delivery_request(seller_whatsapp, user_whatsapp, delivery_address, delivery_id, items, total_price)

            db.session.commit()

            # Send WhatsApp notification to buyer
            notify_buyer_cart_submitted(user_whatsapp, cart, delivery_address, delivery_ids)

            # Store delivery_ids in session
            session['delivery_ids'] = delivery_ids
            session.pop('cart', None)  # Clear cart after checkout

            flash('Demann livrezon voye bay vandè yo! Vandè yo pral mete pri livrezon byento. Ou pral resevwa yon mesaj lè pri yo mete ajou.', 'info')
            return redirect(url_for('cart_success_page'))

    # Calculate cart totals
    cart_items = []
    total_items = 0
    total_price = 0

    for item_ad_id, item_data in cart.items():
        item_ad = Ad.query.filter_by(ad_id=item_ad_id).first()
        if item_ad:
            cart_items.append({
                'ad': item_ad,
                'quantity': item_data['quantity'],
                'subtotal': item_data['price'] * item_data['quantity']
            })
            total_items += item_data['quantity']
            total_price += item_data['price'] * item_data['quantity']

    return render_template('shopping_cart.html', ad=ad, cart=cart, cart_items=cart_items, total_items=total_items, total_price=total_price)

@app.route('/cart_success')
def cart_success_page():
    # Get delivery_ids from session
    delivery_ids = session.get('delivery_ids', [])
    if not delivery_ids:
        flash('Sesyon ekspire. Eseye ankò.', 'error')
        return redirect(url_for('achte'))

    # Get all deliveries for this cart
    deliveries = Delivery.query.filter(Delivery.delivery_id.in_(delivery_ids)).all()
    if not deliveries:
        flash('Erè nan sesyon. Eseye ankò.', 'error')
        return redirect(url_for('achte'))

    # Group deliveries by seller for display
    seller_deliveries = {}
    total_cart_price = 0
    for delivery in deliveries:
        seller = delivery.seller_whatsapp
        if seller not in seller_deliveries:
            seller_deliveries[seller] = []
        seller_deliveries[seller].append(delivery)
        total_cart_price += delivery.total_price

    # Get cart items for display
    cart_items = []
    for delivery in deliveries:
        if delivery.cart_items:
            items = json.loads(delivery.cart_items)
            for item in items:
                ad = Ad.query.filter_by(ad_id=item['ad_id']).first()
                if ad:
                    cart_items.append({
                        'ad': ad,
                        'quantity': item['quantity'],
                        'subtotal': item['price'] * item['quantity']
                    })

    return render_template('cart_success.html', deliveries=deliveries, seller_deliveries=seller_deliveries, cart_items=cart_items, total_cart_price=total_cart_price)

@app.route('/achte/check_balance/<ad_id>', methods=['GET'])
def check_balance(ad_id):
    # Get delivery_id from session
    delivery_id = session.get('delivery_id')

    if not delivery_id:
        flash('Sesyon ekspire. Eseye ankò.', 'error')
        return redirect(url_for('achte'))

    delivery = Delivery.query.filter_by(delivery_id=delivery_id).first()
    if not delivery or delivery.ad_id != ad_id:
        flash('Erè nan sesyon. Eseye ankò.', 'error')
        return redirect(url_for('achte'))

    ad = Ad.query.filter_by(ad_id=ad_id, admin_status='approved').first()
    if not ad:
        flash('Piblisite pa jwenn.', 'error')
        return redirect(url_for('achte'))

    user_gkach = UserGkach.query.filter_by(user_whatsapp=delivery.buyer_whatsapp).first()
    balance = user_gkach.gkach_balance if user_gkach else 0

    # Total price includes ad price + delivery cost
    total_price = delivery.total_price + delivery.delivery_cost

    return render_template('check_balance.html', balance=balance, ad=ad, whatsapp=delivery.buyer_whatsapp, price=total_price, delivery=delivery)

@app.route('/achte_gkach', methods=['GET', 'POST'])
def achte_gkach():
    if request.method == 'POST':
        user_whatsapp = request.form.get('whatsapp', '').strip()
        amount = request.form.get('amount', '').strip()

        # Format WhatsApp number
        user_whatsapp = ''.join(filter(str.isdigit, user_whatsapp))
        if not user_whatsapp.startswith('509'):
            user_whatsapp = '509' + user_whatsapp
        user_whatsapp = '+' + user_whatsapp

        if not user_whatsapp or len(user_whatsapp) < 12:
            flash('Numéro WhatsApp valab obligatwa.', 'error')
            return redirect(url_for('achte_gkach'))
        try:
            amount = int(amount)
            if amount <= 0:
                raise ValueError
        except ValueError:
            flash('Kantite Gkach valab obligatwa.', 'error')
            return redirect(url_for('achte_gkach'))

        # Check terms acceptance
        if not request.form.get('accept_terms'):
            flash('Ou dwe aksepte kondisyon ak règleman yo pou achte Gkach.', 'error')
            return redirect(url_for('achte_gkach'))

        # Get or create user gkach record
        user_gkach = UserGkach.query.filter_by(user_whatsapp=user_whatsapp).first()
        if not user_gkach:
            user_gkach = UserGkach(user_whatsapp=user_whatsapp)
            db.session.add(user_gkach)

        # Add request to pending WITHOUT document (will be uploaded in next step)
        request_id = str(uuid.uuid4())
        requests = json.loads(user_gkach.gkach_requests or '[]')
        requests.append({
            'request_id': request_id,
            'amount': amount,
            'status': 'pending',
            'document': None,  # No document yet
            'requested_at': datetime.now().isoformat()
        })
        user_gkach.gkach_requests = json.dumps(requests)
        db.session.commit()

        # Send WhatsApp notification to admin
        notify_admin_new_gkach_request(user_whatsapp, amount, request_id)

        flash('Demann Gkach ou a soumèt! Kounye a, telechaje prèv pèman ou a.', 'success')
        return redirect(url_for('upload_gkach_approval', request_id=request_id))

    return render_template('achte_gkach.html')

@app.route('/achte/buy/<ad_id>', methods=['POST'])
def buy_ad(ad_id):
    # Get delivery_id from session
    delivery_id = session.get('delivery_id')

    if not delivery_id:
        flash('Sesyon ekspire. Eseye ankò.', 'error')
        return redirect(url_for('achte'))

    delivery = Delivery.query.filter_by(delivery_id=delivery_id, ad_id=ad_id).first()
    if not delivery:
        flash('Erè nan sesyon. Eseye ankò.', 'error')
        return redirect(url_for('achte'))

    ad = Ad.query.filter_by(ad_id=ad_id, admin_status='approved').first()
    if not ad:
        flash('Piblisite pa jwenn.', 'error')
        return redirect(url_for('achte'))

    # Total price includes ad price + delivery cost
    total_price = delivery.total_price + delivery.delivery_cost

    user_gkach = UserGkach.query.filter_by(user_whatsapp=delivery.buyer_whatsapp).first()
    if not user_gkach or user_gkach.gkach_balance < total_price:
        flash('Ou pa gen ase Gkach pou achte piblisite sa a. Ou bezwen achte Gkach.', 'error')
        return redirect(url_for('achte_gkach'))

    # Deduct balance from buyer
    user_gkach.gkach_balance -= total_price

    # Credit balance to seller
    seller_gkach = UserGkach.query.filter_by(user_whatsapp=delivery.seller_whatsapp).first()
    if seller_gkach:
        seller_gkach.gkach_balance += total_price

    db.session.commit()

    # Update delivery status to 'completed'
    delivery.status = 'completed'
    db.session.commit()

    # Clear session
    session.pop('delivery_id', None)

    # Notify admin and user of the purchase
    notify_admin_ad_purchased(delivery.buyer_whatsapp, ad_id, total_price)
    notify_user_ad_purchased(delivery.buyer_whatsapp, ad_id, total_price)

    flash(f'Achte avèk siksè! Ou te depanse {total_price} Gkach.', 'success')
    return redirect(url_for('achte'))

@app.route('/admin/manage_gkach', methods=['GET', 'POST'])
def manage_gkach():
    if 'admin' not in session:
        return redirect(url_for('admin_login'))

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'set_rate':
            currency = request.form.get('currency')
            rate = float(request.form.get('rate', 0))

            # Update or create rate
            gkach_rate = GkachRate.query.filter_by(currency=currency).first()
            if not gkach_rate:
                gkach_rate = GkachRate(currency=currency, rate_per_gkach=rate)
                db.session.add(gkach_rate)
            else:
                gkach_rate.rate_per_gkach = rate
            db.session.commit()
            flash(f'Taux pou {currency} mete ajou a {rate}.', 'success')
            return redirect(url_for('manage_gkach'))

        user_whatsapp = request.form.get('whatsapp')
        amount = int(request.form.get('amount', 0))

        user_gkach = UserGkach.query.filter_by(user_whatsapp=user_whatsapp).first()
        if not user_gkach:
            flash('Itilizatè pa jwenn.', 'error')
            return redirect(url_for('manage_gkach'))

        if action == 'add_balance':
            user_gkach.gkach_balance += amount
            notify_admin_balance_change(user_whatsapp, f"Added {amount}", amount)
            flash(f'{amount} Gkach ajoute nan balans {user_whatsapp}.', 'success')
        elif action == 'edit_balance':
            user_gkach.gkach_balance = amount
            flash(f'Balans Gkach modifye a {amount} pou {user_whatsapp}.', 'success')
        elif action == 'delete_user':
            db.session.delete(user_gkach)
            flash(f'Itilizatè {user_whatsapp} efase avèk siksè.', 'success')
            db.session.commit()
            return redirect(url_for('manage_gkach'))
        elif action == 'approve_request':
            request_id = request.form.get('request_id')
            requests = json.loads(user_gkach.gkach_requests or '[]')
            for req in requests:
                if req.get('request_id') == request_id and req['status'] == 'pending' and req.get('document'):
                    req['status'] = 'approved'
                    user_gkach.gkach_balance += req['amount']
                    notify_admin_request_approved(user_whatsapp, req['amount'], req['request_id'])
                    notify_user_gkach_request_approved(user_whatsapp, req['amount'])
                    flash(f'Demann Gkach apwouve pou {user_whatsapp}.', 'success')
                    break
            user_gkach.gkach_requests = json.dumps(requests)
        elif action == 'reject_request':
            request_id = request.form.get('request_id')
            requests = json.loads(user_gkach.gkach_requests or '[]')
            for req in requests:
                if req.get('request_id') == request_id and req['status'] == 'pending':
                    req['status'] = 'rejected'
                    notify_admin_request_rejected(user_whatsapp, req['amount'], req['request_id'])
                    notify_user_gkach_request_rejected(user_whatsapp, req['amount'])
                    flash(f'Demann Gkach rejte pou {user_whatsapp}.', 'info')
                    break
            user_gkach.gkach_requests = json.dumps(requests)

        db.session.commit()
        return redirect(url_for('manage_gkach'))

    # GET: show all users with gkach
    users_gkach = UserGkach.query.all()
    return render_template('admin_manage_gkach.html', users_gkach=users_gkach)

@app.route('/api/batch/<batch_id>/share', methods=['POST'])
def share_batch(batch_id):
    # Basic check: ensure batch_id is provided and valid
    if not batch_id:
        return jsonify({'success': False, 'message': 'ID gwoup manke.'}), 400

    try:
        batch = Batch.query.filter_by(batch_id=batch_id).first()
        if not batch:
            return jsonify({'success': False, 'message': 'Gwoup pa egziste.'}), 404

        batch.share_count += 1
        batch.click_rewards += 50
        db.session.commit()

        return jsonify({'success': True, 'message': '50 klike ajoute nan rekonpans w!'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Erè nan pataje gwoup la.'}), 500

@app.route('/api/gkach_rate', methods=['GET'])
def get_gkach_rate():
    try:
        # Get the current rate, default to HTG if available, else USD, else default 50
        rate = GkachRate.query.filter_by(currency='HTG').first()
        if not rate:
            rate = GkachRate.query.filter_by(currency='USD').first()
        if rate:
            return jsonify({'rate': rate.rate_per_gkach, 'currency': rate.currency})
        else:
            return jsonify({'rate': 50, 'currency': 'HTG'})  # Default rate
    except Exception as e:
        logger.error(f"Error fetching Gkach rate: {str(e)}")
        return jsonify({'rate': 50, 'currency': 'HTG'}), 500

@app.route('/admin/delete_ad/<ad_id>', methods=['POST'])
def delete_ad(ad_id):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    try:
        ad = Ad.query.filter_by(ad_id=ad_id).first()
        if not ad:
            flash('Piblisite pa jwenn.', 'error')
            return redirect(url_for('admin'))

        batch_id = ad.batch_id
        if batch_id:
            # Remove from batch and replace with next approved ad
            batch = Batch.query.filter_by(batch_id=batch_id).first()
            ad_ids = batch.ads.split(',')
            ad_ids.remove(ad_id)

            # Find next approved ad not in any batch
            next_ad = Ad.query.filter_by(admin_status='approved', batch_id=None).first()

            if next_ad:
                ad_ids.append(next_ad.ad_id)
                # Update batch ads
                batch.ads = ','.join(ad_ids)
                # Update new ad's batch_id
                next_ad.batch_id = batch_id
            else:
                # No replacement, check if batch still has 5 ads
                if len(ad_ids) < 5:
                    # Delete the batch
                    Ad.query.filter_by(batch_id=batch_id).update({'batch_id': None})
                    db.session.delete(batch)
                    flash('Gwoup la efase paske li pa gen ase piblisite apwouve.', 'info')
                    batch_id = None  # Prevent further processing

        # Delete the ad
        db.session.delete(ad)
        db.session.commit()
        flash('Piblisite a efase avèk siksè!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Erè nan efasman piblisite a.', 'error')

    return redirect(url_for('admin'))

@app.route('/admin/delete_batch/<batch_id>', methods=['POST'])
def delete_batch(batch_id):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    try:
        Ad.query.filter_by(batch_id=batch_id).update({'batch_id': None})
        batch = Batch.query.filter_by(batch_id=batch_id).first()
        if batch:
            db.session.delete(batch)
        db.session.commit()

        flash('Gwoup la efase avèk siksè!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Erè nan efasman gwoup la.', 'error')

    return redirect(url_for('admin'))

@app.route('/admin/edit_batch/<batch_id>')
def edit_batch(batch_id):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))

    batch = Batch.query.filter_by(batch_id=batch_id).first()
    if not batch:
        flash('Gwoup pa jwenn.', 'error')
        return redirect(url_for('admin'))

    ad_ids = batch.ads.split(',')
    batch_ads = Ad.query.filter(Ad.ad_id.in_(ad_ids)).all()

    # Get approved ads not in any batch
    available_ads = Ad.query.filter_by(admin_status='approved', batch_id=None).all()

    return render_template('admin_edit_batch.html', batch=batch, batch_ads=batch_ads, available_ads=available_ads)

@app.route('/admin/add_ad_to_batch/<batch_id>/<ad_id>', methods=['POST'])
def add_ad_to_batch(batch_id, ad_id):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))

    batch = Batch.query.filter_by(batch_id=batch_id).first()
    ad = Ad.query.filter_by(ad_id=ad_id, admin_status='approved', batch_id=None).first()

    if not batch or not ad:
        flash('Gwoup oubyen piblisite pa jwenn.', 'error')
        return redirect(url_for('edit_batch', batch_id=batch_id))

    # Add ad to batch
    ad_ids = batch.ads.split(',')
    ad_ids.append(ad_id)
    batch.ads = ','.join(ad_ids)
    ad.batch_id = batch_id

    # Update Open Graph data
    og_data = {
        'title': 'Glory2yahPub Ad Batch',
        'description': 'Check out these amazing ads from Glory2yahPub!',
        'url': url_for('view_batch', batch_id=batch_id, _external=True),
        'images': []
    }
    for ad_id in ad_ids:
        ad = Ad.query.filter_by(ad_id=ad_id).first()
        if ad:
            first_image = ad.images.split(',')[0]
            image_url = url_for('static', filename='uploads/' + first_image, _external=True)
            og_data['images'].append(image_url)
    batch.open_graph_data = json.dumps(og_data)

    db.session.commit()

    flash('Piblisite ajoute nan gwoup avèk siksè!', 'success')
    return redirect(url_for('edit_batch', batch_id=batch_id))

@app.route('/admin/remove_ad_from_batch/<batch_id>/<ad_id>', methods=['POST'])
def remove_ad_from_batch(batch_id, ad_id):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))

    batch = Batch.query.filter_by(batch_id=batch_id).first()
    ad = Ad.query.filter_by(ad_id=ad_id, batch_id=batch_id).first()

    if not batch or not ad:
        flash('Gwoup oubyen piblisite pa jwenn.', 'error')
        return redirect(url_for('edit_batch', batch_id=batch_id))

    # Remove ad from batch
    ad_ids = batch.ads.split(',')
    ad_ids.remove(ad_id)
    batch.ads = ','.join(ad_ids)
    ad.batch_id = None

    # Update Open Graph data
    if ad_ids:
        og_data = {
            'title': 'Glory2yahPub Ad Batch',
            'description': 'Check out these amazing ads from Glory2yahPub!',
            'url': url_for('view_batch', batch_id=batch_id, _external=True),
            'images': []
        }
        for ad_id in ad_ids:
            ad = Ad.query.filter_by(ad_id=ad_id).first()
            if ad:
                first_image = ad.images.split(',')[0]
                image_url = url_for('static', filename='uploads/' + first_image, _external=True)
                og_data['images'].append(image_url)
        batch.open_graph_data = json.dumps(og_data)
    else:
        # If no ads left, delete the batch
        db.session.delete(batch)
        db.session.commit()
        flash('Gwoup la efase paske li pa gen ase piblisite.', 'info')
        return redirect(url_for('admin'))

    db.session.commit()

    flash('Piblisite retire nan gwoup avèk siksè!', 'success')
    return redirect(url_for('edit_batch', batch_id=batch_id))

@app.route('/set_delivery/<delivery_id>', methods=['GET', 'POST'])
def set_delivery(delivery_id):
    delivery = Delivery.query.filter_by(delivery_id=delivery_id).first()
    if not delivery:
        flash('Demann livrezon pa jwenn.', 'error')
        return redirect(url_for('index'))

    ad = Ad.query.filter_by(ad_id=delivery.ad_id).first()
    if not ad:
        flash('Piblisite pa jwenn.', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        delivery_cost = request.form.get('delivery_cost', '').strip()
        notes = request.form.get('notes', '').strip()

        try:
            delivery_cost = int(delivery_cost)
            if delivery_cost < 0:
                raise ValueError
        except ValueError:
            flash('Pri livrezon valab obligatwa.', 'error')
            return redirect(url_for('set_delivery', delivery_id=delivery_id))

        # Check terms acceptance
        if not request.form.get('accept_terms'):
            flash('Ou dwe aksepte kondisyon ak règleman yo.', 'error')
            return redirect(url_for('set_delivery', delivery_id=delivery_id))

        # Update delivery cost
        delivery.delivery_cost = delivery_cost
        delivery.status = 'price_set'
        db.session.commit()

        # Send WhatsApp notification to buyer with updated price
        total_price = delivery.total_price + delivery_cost
        notify_buyer_delivery_updated(delivery.buyer_whatsapp, delivery_cost, total_price, delivery_id)

        flash('Pri livrezon mete ajou avèk siksè! Achete a resevwa mesaj WhatsApp.', 'success')
        return redirect(url_for('index'))

    return render_template('set_delivery.html', delivery=delivery, ad=ad)

# Communication API routes
@app.route('/api/delivery/<delivery_id>/messages', methods=['GET'])
def get_delivery_messages(delivery_id):
    user_whatsapp = request.args.get('whatsapp')
    if not user_whatsapp:
        return jsonify({'error': 'WhatsApp number required'}), 400

    try:
        messages = get_messages(delivery_id, user_whatsapp)
        return jsonify({'messages': messages})
    except ValueError as e:
        return jsonify({'error': str(e)}), 403

@app.route('/api/delivery/<delivery_id>/send_message', methods=['POST'])
def send_delivery_message(delivery_id):
    data = request.get_json()
    sender_whatsapp = data.get('sender_whatsapp')
    message = data.get('message')

    if not sender_whatsapp or not message:
        return jsonify({'error': 'Sender WhatsApp and message required'}), 400

    try:
        new_message = send_message(delivery_id, sender_whatsapp, message)
        return jsonify({
            'message': 'Message sent successfully',
            'message_id': new_message.id,
            'created_at': new_message.created_at.isoformat()
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 403

@app.route('/api/delivery/<delivery_id>/participants', methods=['GET'])
def get_delivery_participants_api(delivery_id):
    try:
        participants = get_delivery_participants(delivery_id)
        return jsonify(participants)
    except ValueError as e:
        return jsonify({'error': str(e)}), 404

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
