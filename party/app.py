from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, current_app, Response
from flask_wtf.csrf import CSRFProtect, CSRFError
import os
import uuid
from datetime import datetime
from app import db, csrf, limiter, cache
from app.models.party import Party, PartyParticipant
from app.models.user import User
from app.models.user_gkach import UserGkach
from app.utils.validators import validate_whatsapp
from flask_login import current_user

ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024


def parse_price(value):
    try:
        price = int(str(value or "0").strip())
    except (TypeError, ValueError):
        raise ValueError("Pri a dwe yon nonb antye.")
    if price < 0:
        raise ValueError("Pri a pa ka negatif.")
    return price


def save_party_photo(photo):
    if not photo or not photo.filename:
        return None
    from werkzeug.utils import secure_filename

    filename = secure_filename(photo.filename)
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError("Foto a dwe JPG, PNG oswa WEBP.")
    photo.stream.seek(0, os.SEEK_END)
    size = photo.stream.tell()
    photo.stream.seek(0)
    if size > MAX_IMAGE_BYTES:
        raise ValueError("Foto a twò gwo. Limit la se 5 MB.")
    stored_name = f"party_{uuid.uuid4()}.{extension}"
    os.makedirs("static/uploads", exist_ok=True)
    photo.save(os.path.join("static/uploads", stored_name))
    return stored_name

party_bp = Blueprint('party', __name__)

# P1 FIX V11 — NO MORE csrf.exempt(party_bp) blanket bypass.
# All party forms now send the CSRF token via {{ csrf_token() }} or
# fetch() with X-CSRFToken header (base.html meta tag).
# Webhook-ish endpoints that truly need exemption must be added selectively
# (none at this time). Blanket exempt = REMOVED.


def get_party_models():
    return Party, PartyParticipant


@party_bp.context_processor
def inject_party_data():
    try:
        # Cache parties list for 60 seconds to reduce DB load on every request
        # Cache key includes a version suffix so we can invalidate on party changes
        cache_key = 'party_module:all_parties:v1'
        cached = cache.get(cache_key)
        if cached is not None:
            parties = cached
        else:
            Party, PartyParticipant = get_party_models()
            parties = Party.query.order_by(Party.date.desc()).all()
            try:
                cache.set(cache_key, parties, timeout=60)
            except Exception:
                pass  # Cache may not be available; proceed without it
        
        # Get user info for the main app context
        user = None
        gkach_balance = 0
        is_logged_in = False
        
        if current_user.is_authenticated:
            user = current_user
            is_logged_in = True
            user_gkach = UserGkach.query.filter_by(user_whatsapp=user.whatsapp).first()
            gkach_balance = user_gkach.gkach_balance if user_gkach else 0
        
        return {
            'parties': parties, 
            'party_module': True,
            'current_user': user,
            'gkach_balance': gkach_balance,
            'is_logged_in': is_logged_in
        }
    except Exception as e:
        # If database tables don't exist or other errors, return empty data
        return {'parties': [], 'party_module': True, 'current_user': None, 'gkach_balance': 0, 'is_logged_in': False}


@party_bp.route('/')
def index():
    Party, PartyParticipant = get_party_models()
    page = request.args.get('page', 1, type=int)
    per_page = 20
    pagination = Party.query.order_by(Party.date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    parties = pagination.items
    return render_template('party/index.html', parties=parties, pagination=pagination, page=page)


@party_bp.route('/<party_id>')
def party_detail(party_id):
    Party, PartyParticipant = get_party_models()
    party = Party.query.filter_by(party_id=party_id).first()
    if not party:
        flash('Fèt la pa egziste.', 'error')
        return redirect(url_for('party.index'))
    
    participants = PartyParticipant.query.filter_by(party_id=party_id).all()
    is_owner = is_party_owner(party_id)
    
    import json
    food_options = json.loads(party.food_options) if party.food_options else []
    drink_options = json.loads(party.drink_options) if party.drink_options else []
    
    return render_template(
        'party/detail.html',
        party=party,
        participants=participants if is_owner else [],
        participant_count=len(participants),
        is_owner=is_owner,
        food_options=food_options,
        drink_options=drink_options,
    )


@party_bp.route('/register/<party_id>', methods=['POST'])
@limiter.limit("10 per minute")
def register(party_id):
    Party, PartyParticipant = get_party_models()
    party = Party.query.filter_by(party_id=party_id).first()
    if not party:
        flash('Fèt la pa egziste.', 'error')
        return redirect(url_for('party.index'))

    if party.date < datetime.utcnow().date():
        flash('Enskripsyon pou fèt sa a fini.', 'error')
        return redirect(url_for('party.party_detail', party_id=party_id))
    
    name = request.form.get('name', '').strip()
    whatsapp = request.form.get('whatsapp', '').strip()
    food_choice = request.form.get('food_choice', '')
    drink_choice = request.form.get('drink_choice', '')
    
    # Get user_id from session if logged in
    user_id = None
    if current_user.is_authenticated:
        user_id = current_user.id
        if not name:
            name = current_user.name or current_user.pseudo
        if not whatsapp and current_user.whatsapp:
            whatsapp = current_user.whatsapp
    
    if not name or not whatsapp:
        flash('Non ak WhatsApp obligatwa.', 'error')
        return redirect(url_for('party.party_detail', party_id=party_id))
    
    try:
        whatsapp = validate_whatsapp(whatsapp)
    except:
        pass
    
    # Check if already registered
    existing = PartyParticipant.query.filter_by(party_id=party_id, whatsapp=whatsapp).first()
    if existing:
        flash('Ou deja enskri pou fèt sa a.', 'info')
        return redirect(url_for('party.party_detail', party_id=party_id))
    
    # Create participant - link to user profile if logged in
    participant = PartyParticipant(
        party_id=party_id,
        user_id=user_id,
        name=name,
        whatsapp=whatsapp,
        food_choice=food_choice,
        drink_choice=drink_choice
    )
    try:
        db.session.add(participant)
        db.session.commit()
        # Invalidate parties cache (participant count may affect display)
        try:
            cache.delete('party_module:all_parties:v1')
        except Exception:
            pass
    except Exception as e:
        db.session.rollback()
        flash(f'Erè enskri: {str(e)}', 'error')
        return redirect(url_for('party.party_detail', party_id=party_id))
    
    flash('Ou enskri avèk siksè pou fèt la!', 'success')
    return redirect(url_for('party.party_detail', party_id=party_id))


@party_bp.route('/admin/parties', methods=['GET', 'POST'])
@limiter.limit("30 per minute")
def admin_parties():
    Party, PartyParticipant = get_party_models()
    
    # Check admin session
    if 'admin' not in session:
        flash('Ou dwe konekte kòm administratè.', 'error')
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'create':
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            date_str = request.form.get('date', '').strip()
            location = request.form.get('location', '').strip()
            price = request.form.get('price', '0').strip()
            
            if not name or not date_str:
                flash('Non ak dat obligatwa.', 'error')
                return redirect(url_for('party.admin_parties'))
            
            try:
                party_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Dat envalid.', 'error')
                return redirect(url_for('party.admin_parties'))
            
            # Handle photo upload
            photo_filename = None
            if 'photo' in request.files:
                photo = request.files['photo']
                if photo and photo.filename:
                    from werkzeug.utils import secure_filename
                    filename = f"party_{uuid.uuid4()}_{secure_filename(photo.filename)}"
                    photo_path = os.path.join('static/uploads', filename)
                    try:
                        os.makedirs('static/uploads', exist_ok=True)
                        photo.save(photo_path)
                        photo_filename = filename
                    except Exception:
                        pass
            
            owner_code = generate_owner_code()
            
            party = Party(
                name=name,
                description=description,
                date=party_date,
                location=location,
                price=int(price) if price else 0,
                photo=photo_filename,
                owner_code=owner_code
            )
            try:
                db.session.add(party)
                db.session.commit()
                # Invalidate parties cache so context processor picks up new party
                try:
                    cache.delete('party_module:all_parties:v1')
                except Exception:
                    pass
            except Exception as e:
                db.session.rollback()
                flash(f'Erè kreye fèt: {str(e)}', 'error')
                return redirect(url_for('party.admin_parties'))
            flash('Fèt kreye avèk siksè!', 'success')
            return redirect(url_for('party.admin_parties'))
        
        elif action == 'delete':
            party_id = request.form.get('party_id')
            party = Party.query.filter_by(party_id=party_id).first()
            if party:
                try:
                    # Delete participants first
                    PartyParticipant.query.filter_by(party_id=party_id).delete()
                    db.session.delete(party)
                    db.session.commit()
                    flash('Fèt efase avèk siksè!', 'success')
                except Exception as e:
                    db.session.rollback()
                    flash(f'Erè efase fèt: {str(e)}', 'error')
            return redirect(url_for('party.admin_parties'))
    
    # Use cached parties list from context processor when possible
    try:
        cached_parties = cache.get('party_module:all_parties:v1')
        if cached_parties is None:
            raise KeyError('not cached')
        parties = cached_parties
    except Exception:
        Party, PartyParticipant = get_party_models()
        parties = Party.query.order_by(Party.date.desc()).all()
    
    return render_template('party/admin_parties.html', parties=parties)


@party_bp.route('/admin/party/<party_id>')
def admin_party_detail(party_id):
    Party, PartyParticipant = get_party_models()
    
    if 'admin' not in session:
        flash('Ou dwe konekte kòm administratè.', 'error')
        return redirect(url_for('main.index'))
    
    party = Party.query.filter_by(party_id=party_id).first()
    if not party:
        flash('Fèt la pa egziste.', 'error')
        return redirect(url_for('party.admin_parties'))
    
    participants = PartyParticipant.query.filter_by(party_id=party_id).order_by(PartyParticipant.created_at.desc()).all()
    return render_template('party/admin_detail.html', party=party, participants=participants)


@party_bp.route('/admin/party/<party_id>/export.csv')
def export_participants(party_id):
    Party, PartyParticipant = get_party_models()
    party = Party.query.filter_by(party_id=party_id).first()
    if not party:
        flash('Fèt la pa egziste.', 'error')
        return redirect(url_for('party.index'))
    if not is_party_owner(party_id):
        flash('Sèlman pwoprietè fèt la ka ekspòte patisipan yo.', 'error')
        return redirect(url_for('party.party_detail', party_id=party_id))

    participants = PartyParticipant.query.filter_by(party_id=party_id).order_by(
        PartyParticipant.created_at.asc()
    ).all()
    rows = ["No,Non,WhatsApp,Manje,Bwason,Dat inscription"]
    for number, participant in enumerate(participants, start=1):
        values = [
            number,
            participant.name,
            participant.whatsapp,
            participant.food_choice or "",
            participant.drink_choice or "",
            participant.created_at.isoformat() if participant.created_at else "",
        ]
        rows.append(",".join('"' + str(value).replace('"', '""') + '"' for value in values))
    body = "\ufeff" + "\n".join(rows) + "\n"
    return Response(
        body,
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="participants-{party_id[:8]}.csv"'},
    )


def generate_owner_code():
    import string
    import random
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=6))


@party_bp.route('/kreye', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def create_party():
    Party, PartyParticipant = get_party_models()
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        date_str = request.form.get('date', '').strip()
        location = request.form.get('location', '').strip()
        price = request.form.get('price', '0').strip()
        
        if not name or not date_str:
            flash('Non fèt ak dat obligatwa.', 'error')
            return redirect(url_for('party.create_party'))
        
        try:
            party_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Dat envalid. Sèvi fòma: YYYY-MM-DD', 'error')
            return redirect(url_for('party.create_party'))
        
        try:
            party_price = parse_price(price)
            photo_filename = save_party_photo(request.files.get("photo"))
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("party.create_party"))
        
        # Get user_id from session if logged in
        user_id = None
        if current_user.is_authenticated:
            user_id = current_user.id
        
        # Generate unique owner code
        owner_code = generate_owner_code()
        
        party = Party(
            user_id=user_id,
            name=name,
            description=description,
            date=party_date,
            location=location,
            price=party_price,
            photo=photo_filename,
            owner_code=owner_code
        )
        try:
            db.session.add(party)
            db.session.commit()
            # Invalidate parties cache so context processor picks up new party
            try:
                cache.delete('party_module:all_parties:v1')
            except Exception:
                pass
        except Exception as e:
            db.session.rollback()
            flash(f'Erè kreye fèt: {str(e)}', 'error')
            return redirect(url_for('party.create_party'))
        
        flash('Fèt ou a kreye avèk siksè! Sèvi ak kòd pwoprietè a pou konekte tounen.', 'success')
        return redirect(url_for('party.party_detail', party_id=party.party_id))
    
    return render_template('party/create.html')


@party_bp.route('/my-parties')
def my_parties():
    Party, PartyParticipant = get_party_models()
    
    if not current_user.is_authenticated:
        flash('Ou dwe konekte pou wè fèt ou yo kreye.', 'error')
        return redirect(url_for('auth.login'))
    
    # Show parties created by this user
    parties = Party.query.filter_by(user_id=current_user.id).order_by(Party.date.desc()).all()
    return render_template('party/my_parties.html', parties=parties)


@party_bp.route('/manage/<party_id>/options', methods=['GET', 'POST'])
def manage_options(party_id):
    Party, PartyParticipant = get_party_models()
    
    party = Party.query.filter_by(party_id=party_id).first()
    if not party:
        flash('Fèt la pa egziste.', 'error')
        return redirect(url_for('party.index'))
    
    if not is_party_owner(party_id):
        flash('Sèlman pwoprietè fèt la ka jere opsyon.', 'error')
        return redirect(url_for('party.party_detail', party_id=party_id))
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        import json
        
        food_options = json.loads(party.food_options) if party.food_options else []
        drink_options = json.loads(party.drink_options) if party.drink_options else []
        
        if action == 'add_food':
            food_name = request.form.get('food_name', '').strip()
            if food_name and food_name not in food_options:
                food_options.append(food_name)
                flash(f'Manje "{food_name}" ajoute.', 'success')
        
        elif action == 'add_drink':
            drink_name = request.form.get('drink_name', '').strip()
            if drink_name and drink_name not in drink_options:
                drink_options.append(drink_name)
                flash(f'Bwason "{drink_name}" ajoute.', 'success')
        
        elif action == 'remove_food':
            food_name = request.form.get('food_name', '').strip()
            if food_name in food_options:
                food_options.remove(food_name)
                flash(f'Manje "{food_name}" efase.', 'success')
        
        elif action == 'remove_drink':
            drink_name = request.form.get('drink_name', '').strip()
            if drink_name in drink_options:
                drink_options.remove(drink_name)
                flash(f'Bwason "{drink_name}" efase.', 'success')
        
        elif action == 'update_food':
            old_name = request.form.get('old_name', '').strip()
            new_name = request.form.get('new_name', '').strip()
            if old_name in food_options and new_name:
                food_options[food_options.index(old_name)] = new_name
                flash(f'Manje modifye.', 'success')
        
        elif action == 'update_drink':
            old_name = request.form.get('old_name', '').strip()
            new_name = request.form.get('new_name', '').strip()
            if old_name in drink_options and new_name:
                drink_options[drink_options.index(old_name)] = new_name
                flash(f'Bwason modifye.', 'success')
        
        # Save updated options
        try:
            party.food_options = json.dumps(food_options)
            party.drink_options = json.dumps(drink_options)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f'Erè modifie opsyon: {str(e)}', 'error')
            return redirect(url_for('party.manage_options', party_id=party_id))
        
        return redirect(url_for('party.manage_options', party_id=party_id))
    
    import json
    food_options = json.loads(party.food_options) if party.food_options else []
    drink_options = json.loads(party.drink_options) if party.drink_options else []
    
    return render_template('party/manage_options.html', party=party, food_options=food_options, drink_options=drink_options)


@party_bp.route('/api/party/<party_id>/options', methods=['GET'])
def get_party_options(party_id):
    Party, _ = get_party_models()
    
    party = Party.query.filter_by(party_id=party_id).first()
    if not party:
        return jsonify({'error': 'Party not found'}), 404
    
    import json
    return jsonify({
        'food_options': json.loads(party.food_options) if party.food_options else [],
        'drink_options': json.loads(party.drink_options) if party.drink_options else []
    })


@party_bp.route('/send_group_message/<party_id>', methods=['GET', 'POST'])
def send_group_message(party_id):
    Party, PartyParticipant = get_party_models()
    
    party = Party.query.filter_by(party_id=party_id).first()
    if not party:
        flash('Fèt la pa egziste.', 'error')
        return redirect(url_for('party.index'))
    
    if not is_party_owner(party_id):
        flash('Sèlman pwoprietè fèt la ka voye mesaj group.', 'error')
        return redirect(url_for('party.party_detail', party_id=party_id))
    
    participants = PartyParticipant.query.filter_by(party_id=party_id).all()
    
    if not participants:
        flash('Pa gen patisipan pou voye mesaj.', 'error')
        return redirect(url_for('party.party_detail', party_id=party_id))
    
    if request.method == 'POST':
        custom_message = request.form.get('message', '').strip()
        
        try:
            from src.notifications import notify_party_participants
        except ImportError:
            try:
                from notifications import notify_party_participants
            except ImportError:
                notify_party_participants = None
        
        if notify_party_participants:
            results = notify_party_participants(
                party_name=party.name,
                party_date=party.date,
                party_location=party.location,
                participants=participants,
                custom_message=custom_message
            )
            
            if results:
                session['party_message_results'] = results
                flash(f'Mesaj pwepare pou {len(results)} patisipan! Klik sou chake lyen pou voye mesaj.', 'success')
                return redirect(url_for('party.group_message_results', party_id=party_id))
            else:
                flash('Erè nan pwepare mesaj. Eseye ankò.', 'error')
        else:
            flash('Modil notifikasyon pa disponib.', 'error')
    
    return render_template('party/send_group_message.html', party=party, participants=participants)


@party_bp.route('/group_message_results/<party_id>')
def group_message_results(party_id):
    Party, PartyParticipant = get_party_models()
    
    party = Party.query.filter_by(party_id=party_id).first()
    if not party:
        flash('Fèt la pa egziste.', 'error')
        return redirect(url_for('party.index'))
    
    results = session.get('party_message_results', [])
    
    if not results:
        flash('Pa gen rezilta mesaj.', 'info')
        return redirect(url_for('party.party_detail', party_id=party_id))
    
    return render_template('party/group_message_results.html', party=party, results=results)


@party_bp.route('/api/party/<party_id>/is_owner', methods=['GET'])
def api_party_is_owner(party_id):
    is_owner = is_party_owner(party_id)
    return jsonify({'is_owner': is_owner})


@party_bp.route('/reconnect', methods=['GET', 'POST'])
@limiter.limit("5 per minute", methods=["POST"])
def reconnect():
    Party, PartyParticipant = get_party_models()
    
    if request.method == 'POST':
        party_id = request.form.get('party_id', '').strip()
        owner_code = request.form.get('owner_code', '').strip().upper()
        
        if not party_id or not owner_code:
            flash('Nimewo fè ak kòd pwoprietè obligatwa.', 'error')
            return redirect(url_for('party.reconnect'))
        
        party = Party.query.filter_by(party_id=party_id, owner_code=owner_code).first()
        if not party:
            flash('Fè oubyen kòd pa valid.', 'error')
            return redirect(url_for('party.reconnect'))
        
        # Store party owner session
        session['party_owner_' + party_id] = True
        flash('Ou konekte kòm pwoprietè fè la!', 'success')
        return redirect(url_for('party.party_detail', party_id=party_id))
    
    return render_template('party/reconnect.html')


@party_bp.route('/api/party/reconnect/verify', methods=['POST'])
@limiter.limit("5 per minute")
def verify_reconnect():
    Party, _ = get_party_models()
    
    data = request.get_json()
    party_id = data.get('party_id', '').strip()
    owner_code = data.get('owner_code', '').strip().upper()
    
    if not party_id or not owner_code:
        return jsonify({'valid': False, 'error': 'Party ID and code required'}), 400
    
    party = Party.query.filter_by(party_id=party_id, owner_code=owner_code).first()
    if not party:
        return jsonify({'valid': False, 'error': 'Party or code invalid'}), 404
    
    return jsonify({
        'valid': True,
        'party_name': party.name,
        'party_id': party.party_id
    })


def is_party_owner(party_id):
    # Check if logged in user is owner
    if current_user.is_authenticated:
        party = Party.query.filter_by(party_id=party_id).first()
        if party and party.user_id == current_user.id:
            return True
    
    # Check if via reconnect code
    if session.get('party_owner_' + party_id):
        return True
    
    # Check if admin
    if 'admin' in session:
        return True
    
    return False


@party_bp.route('/owner/edit/<party_id>', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def edit_party(party_id):
    Party, PartyParticipant = get_party_models()
    
    party = Party.query.filter_by(party_id=party_id).first()
    if not party:
        flash('Fèt la pa egziste.', 'error')
        return redirect(url_for('party.index'))
    
    if not is_party_owner(party_id):
        flash('Sèlman pwoprietè fèt la ka modifye fè a.', 'error')
        return redirect(url_for('party.party_detail', party_id=party_id))
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        date_str = request.form.get('date', '').strip()
        location = request.form.get('location', '').strip()
        price = request.form.get('price', '0').strip()
        
        if not name or not date_str:
            flash('Non fèt ak dat obligatwa.', 'error')
            return redirect(url_for('party.edit_party', party_id=party_id))
        
        try:
            party_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Dat envalid. Sèvi fòma: YYYY-MM-DD', 'error')
            return redirect(url_for('party.edit_party', party_id=party_id))
        
        try:
            party_price = parse_price(price)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("party.edit_party", party_id=party_id))

        # Handle photo upload
        if 'photo' in request.files:
            photo = request.files['photo']
            if photo and photo.filename:
                try:
                    new_photo = save_party_photo(photo)
                except ValueError as exc:
                    flash(str(exc), "error")
                    return redirect(url_for("party.edit_party", party_id=party_id))
                if party.photo:
                    old_path = os.path.join('static/uploads', party.photo)
                    if os.path.exists(old_path):
                        try:
                            os.remove(old_path)
                        except Exception:
                            pass
                party.photo = new_photo
        
        # Update party
        party.name = name
        party.description = description
        party.date = party_date
        party.location = location
        party.price = party_price
        
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f'Erè modifye fèt: {str(e)}', 'error')
            return redirect(url_for('party.edit_party', party_id=party_id))
        
        flash('Fè modifye avèk siksè!', 'success')
        return redirect(url_for('party.party_detail', party_id=party_id))
    
    # Decode JSON options for form
    import json
    food_options = json.loads(party.food_options) if party.food_options else []
    drink_options = json.loads(party.drink_options) if party.drink_options else []
    
    return render_template('party/edit_party.html', party=party, food_options=food_options, drink_options=drink_options)


@party_bp.route('/owner/delete/<party_id>', methods=['POST'])
@limiter.limit("5 per minute")
def delete_party(party_id):
    Party, PartyParticipant = get_party_models()
    
    party = Party.query.filter_by(party_id=party_id).first()
    if not party:
        flash('Fèt la pa egziste.', 'error')
        return redirect(url_for('party.index'))
    
    if not is_party_owner(party_id):
        flash('Sèlman pwoprietè fèt la ka efase fè a.', 'error')
        return redirect(url_for('party.party_detail', party_id=party_id))
    
    # Delete party photo if exists
    if party.photo:
        photo_path = os.path.join('static/uploads', party.photo)
        if os.path.exists(photo_path):
            try:
                os.remove(photo_path)
            except Exception:
                pass
    
    # Delete all participants first + party in transaction
    try:
        PartyParticipant.query.filter_by(party_id=party_id).delete()
        db.session.delete(party)
        db.session.commit()
        flash('Fè efase avèk siksè!', 'success')
        # Invalidate parties cache after deletion
        try:
            cache.delete('party_module:all_parties:v1')
        except Exception:
            pass
    except Exception as e:
        db.session.rollback()
        flash(f'Erè efase fèt: {str(e)}', 'error')
    
    return redirect(url_for('party.index'))


@party_bp.route('/api/owner/login', methods=['POST'])
@limiter.limit("5 per minute")
def api_owner_login():
    Party, _ = get_party_models()
    
    data = request.get_json()
    party_id = data.get('party_id', '').strip()
    owner_code = data.get('owner_code', '').strip().upper()
    
    if not party_id or not owner_code:
        return jsonify({'success': False, 'error': 'Party ID and code required'}), 400
    
    party = Party.query.filter_by(party_id=party_id, owner_code=owner_code).first()
    if not party:
        return jsonify({'success': False, 'error': 'Party or code invalid'}), 404
    
    session['party_owner_' + party_id] = True
    
    return jsonify({
        'success': True,
        'party_name': party.name,
        'party_id': party.party_id,
    })


@party_bp.route('/api/party/<party_id>/owner_info', methods=['GET'])
def api_party_owner_info(party_id):
    Party, _ = get_party_models()
    
    party = Party.query.filter_by(party_id=party_id).first()
    if not party:
        return jsonify({'error': 'Party not found'}), 404
    
    response = {
        'party_id': party.party_id,
        'party_name': party.name,
        'is_owner': is_party_owner(party_id),
    }
    if response['is_owner']:
        response['owner_code'] = party.owner_code
    return jsonify(response)


# ── API Error Handlers ───────────────────────────────────────────────────────
@party_bp.errorhandler(429)
def ratelimit_handler(e):
    """Rate limit exceeded — return JSON for API calls, HTML otherwise."""
    if request.path.startswith('/api/'):
        return jsonify({
            'error': 'Rate limit exceeded',
            'message': 'Trop de demann. Eterè yon moman epi eseye ankò.',
            'retry_after': e.description
        }), 429
    flash('Trop de demann. Eterè yon moman epi eseye ankò.', 'error')
    return redirect(url_for('party.index'))


@party_bp.errorhandler(CSRFError)
def csrf_error(e):
    """CSRF token missing/invalid — return JSON for API calls, HTML otherwise."""
    if request.path.startswith('/api/') or request.is_json:
        return jsonify({
            'error': 'CSRF token error',
            'message': 'Li pseen validToken. Rechaje paj la epi eseye ankò.'
        }), 400
    flash('Li pseen validToken. Rechaje paj la epi eseye ankò.', 'error')
    return redirect(url_for('party.index'))