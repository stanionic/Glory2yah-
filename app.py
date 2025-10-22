from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, make_response
from models import db, Ad, Batch
import uuid
import os
import json
from datetime import datetime
from werkzeug.utils import secure_filename
from src.logger import setup_logger

app = Flask(__name__)
app.secret_key = 'glory2yahpub_secret_key_2024'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///glory2yahpub.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# Set up logger
logger = setup_logger()

# Custom Jinja2 filter for fromjson
def fromjson(value):
    return json.loads(value)

app.jinja_env.filters['fromjson'] = fromjson

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

with app.app_context():
    db.create_all()

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == 'StanGlory2YahPub0886':  # Hardcoded for now
            session['admin'] = True
            flash('Logged in as admin.', 'success')
            return redirect(url_for('admin'))
        else:
            flash('Invalid password.', 'error')
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
        description = request.form.get('description', '').strip()

        # Format WhatsApp number: remove non-digits, ensure +509 prefix
        user_whatsapp = ''.join(filter(str.isdigit, user_whatsapp))
        if not user_whatsapp.startswith('509'):
            user_whatsapp = '509' + user_whatsapp
        user_whatsapp = '+' + user_whatsapp

        if not user_whatsapp or len(user_whatsapp) < 12:  # Basic validation for +509xxxxxxxx
            flash('Numéro WhatsApp valab obligatwa (egz: +50912345678).', 'error')
            return redirect(url_for('submit_ad'))
        if not description:
            flash('Deskripsyon piblisite a obligatwa.', 'error')
            return redirect(url_for('submit_ad'))

        images = []
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

        # Ensure upload directory exists
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

        # Now save files
        saved_images = []
        for file in images:
            filename = f"{uuid.uuid4()}_{secure_filename(file.filename)}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            try:
                file.save(filepath)
                saved_images.append(filename)
                logger.info(f"File saved successfully: {filename}")
            except Exception as e:
                logger.error(f"Error saving file {filename}: {str(e)}")
                flash('Erè nan telechajman imaj yo. Eseye ankò.', 'error')
                return redirect(url_for('submit_ad'))

        ad_id = str(uuid.uuid4())
        created_at = datetime.now().isoformat()

        try:
            new_ad = Ad(
                ad_id=ad_id,
                user_whatsapp=user_whatsapp,
                images=','.join(saved_images),
                description=description,
                created_at=datetime.utcnow()
            )
            db.session.add(new_ad)
            db.session.commit()
            logger.info(f"Ad submitted successfully: {ad_id}")
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

@app.route('/success')
def success():
    return render_template('success.html')

@app.route('/admin')
def admin():
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    ads = Ad.query.order_by(Ad.created_at.desc()).all()
    batches = Batch.query.order_by(Batch.created_at.desc()).all()

    return render_template('admin.html', ads=ads, batches=batches)

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
        available_ads = Ad.query.filter_by(admin_status='approved', batch_id=None).limit(5).all()

        if len(available_ads) < 5:
            flash(f'Pa ase piblisite apwouve. Bezwen 5, gen {len(available_ads)} disponib.', 'error')
            return redirect(url_for('admin'))

        batch_id = str(uuid.uuid4())
        ad_ids = [ad.ad_id for ad in available_ads]

        # Generate Open Graph data for carousel
        og_data = {
            'title': 'Glory2yahPub Ad Batch',
            'description': 'Check out these amazing ads from Glory2yahPub!',
            'url': url_for('view_batch', batch_id=batch_id, _external=True),
            'images': []
        }
        for ad in available_ads:
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

        for ad in available_ads:
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
    # Fetch all approved ads
    approved_ads = Ad.query.filter_by(admin_status='approved').order_by(Ad.created_at.desc()).all()
    return render_template('achte.html', ads=approved_ads)

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

if __name__ == '__main__':
    app.run(debug=False)
