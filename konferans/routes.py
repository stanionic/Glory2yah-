from flask import Blueprint, render_template, request, jsonify, session, send_from_directory, current_app
from flask_socketio import emit, join_room, leave_room
from flask_login import login_required, current_user
from app import db
from app.models import KonferansRoom, KonferansRecording, User
from app.utils.security import admin_required
import uuid
import os
import json
import random
import string
from werkzeug.security import generate_password_hash, check_password_hash, safe_join
from werkzeug.utils import secure_filename
from datetime import datetime
import secrets

_ALLOWED_RECORDING_EXTS = {'.webm', '.mp4', '.mkv', '.mov', '.ogg', '.m4v'}
_MAX_RECORDING_MB = 512

konferans_bp = Blueprint('konferans', __name__, url_prefix='/konferans', template_folder='templates')

# Global variables for room management
active_rooms = {}  # room_id: {participants: [], is_recording: False, ...}
room_participants = {}  # room_id: {socket_id: user_name}
room_whiteboard = {}  # room_id: {strokes: [], current_color: '#000000', current_size: 2}
room_polls = {}  # room_id: {poll_id: {question, options, votes, active}}
room_raised_hands = {}  # room_id: [user_name, ...]
room_breakouts = {}  # room_id: {breakout_rooms: [{id, name, participants: []}]}

def register_socketio_handlers(socketio):
    """Register all socketio event handlers"""
    
    @socketio.on('join')
    def handle_join(data):
        """Handle user joining a room"""
        room_id = data.get('room_id')
        user_name = data.get('user_name')

        if not room_id or not user_name:
            return

        # Get room from database to check max participants
        room = KonferansRoom.query.filter_by(room_id=room_id, is_active=True).first()
        if not room:
            emit('join_error', {'message': 'Sal sa pa egziste oubyen li pa aktif.'}, room=request.sid)
            return

        from flask_socketio import join_room, emit
        join_room(room_id)

        # Add participant to room
        if room_id not in active_rooms:
            active_rooms[room_id] = {
                'participants': [],
                'is_recording': False,
                'recording_started_by': None,
                'is_screen_sharing': False,
                'screen_sharer': None
            }

        if user_name not in active_rooms[room_id]['participants']:
            active_rooms[room_id]['participants'].append(user_name)

        room_participants[room_id] = room_participants.get(room_id, {})
        room_participants[room_id][request.sid] = user_name

        # Get list of other participants
        peers = []
        for sid, name in room_participants[room_id].items():
            if sid != request.sid:
                peers.append({'sid': sid, 'user_name': name})

        # Send existing peers to the new user
        emit('all_users', peers, room=request.sid)

        # Send current whiteboard state to new user
        if room_id in room_whiteboard and room_whiteboard[room_id].get('strokes'):
            emit('whiteboard_state', {
                'strokes': room_whiteboard[room_id]['strokes']
            }, room=request.sid)

        # Notify others in room
        emit('user_joined', {
            'sid': request.sid,
            'user_name': user_name,
            'participants': active_rooms[room_id]['participants']
        }, room=room_id, skip_sid=request.sid)

    @socketio.on('sending_signal')
    def handle_sending_signal(data):
        """Handle WebRTC signaling (offer/answer/candidate)"""
        from flask_socketio import emit
        user_to_signal = data.get('user_to_signal')
        signal = data.get('signal')
        
        if user_to_signal and signal:
            emit('user_joined_signal', {
                'signal': signal,
                'caller_id': request.sid,
                'user_name': room_participants.get(data.get('room_id'), {}).get(request.sid, 'Unknown')
            }, room=user_to_signal)

    @socketio.on('chat_message')
    def handle_chat_message(data):
        """Handle chat messages"""
        from flask_socketio import emit
        room_id = data.get('room_id')
        message = data.get('message', '').strip()
        user_name = data.get('user_name')

        if not room_id or not message or not user_name:
            return

        if len(message) > 500:  # Limit message length
            return

        # Broadcast message to room
        emit('chat_message', {
            'user_name': user_name,
            'message': message,
            'timestamp': datetime.now().strftime('%H:%M')
        }, room=room_id)

    @socketio.on('start_recording')
    def handle_start_recording(data):
        """Handle recording start"""
        from flask_socketio import emit
        room_id = data.get('room_id')

        if not room_id or room_id not in active_rooms:
            return

        active_rooms[room_id]['is_recording'] = True
        active_rooms[room_id]['recording_started_by'] = room_participants.get(room_id, {}).get(request.sid)

        emit('recording_started', room=room_id)

    @socketio.on('stop_recording')
    def handle_stop_recording(data):
        """Handle recording stop"""
        from flask_socketio import emit
        room_id = data.get('room_id')

        if not room_id or room_id not in active_rooms:
            return

        active_rooms[room_id]['is_recording'] = False
        active_rooms[room_id]['recording_started_by'] = None

        emit('recording_stopped', room=room_id)

    @socketio.on('start_screen_share')
    def handle_start_screen_share(data):
        """Handle screen sharing start"""
        from flask_socketio import emit
        room_id = data.get('room_id')

        if not room_id or room_id not in active_rooms:
            return

        active_rooms[room_id]['is_screen_sharing'] = True
        active_rooms[room_id]['screen_sharer'] = room_participants.get(room_id, {}).get(request.sid)

        emit('screen_share_started', {
            'sharer': active_rooms[room_id]['screen_sharer']
        }, room=room_id)

    @socketio.on('stop_screen_share')
    def handle_stop_screen_share(data):
        """Handle screen sharing stop"""
        from flask_socketio import emit
        room_id = data.get('room_id')

        if not room_id or room_id not in active_rooms:
            return

        active_rooms[room_id]['is_screen_sharing'] = False
        active_rooms[room_id]['screen_sharer'] = None

        emit('screen_share_stopped', room=room_id)

    @socketio.on('screen_offer')
    def handle_screen_offer(data):
        """Handle screen sharing offer"""
        from flask_socketio import emit
        room_id = data.get('room_id')
        offer = data.get('offer')

        if not room_id or not offer:
            return

        emit('screen_offer', {
            'offer': offer,
            'from': room_participants.get(room_id, {}).get(request.sid)
        }, room=room_id, skip_sid=request.sid)

    @socketio.on('screen_answer')
    def handle_screen_answer(data):
        """Handle screen sharing answer"""
        from flask_socketio import emit
        room_id = data.get('room_id')
        answer = data.get('answer')

        if not room_id or not answer:
            return

        emit('screen_answer', {
            'answer': answer,
            'from': room_participants.get(room_id, {}).get(request.sid)
        }, room=room_id, skip_sid=request.sid)

    @socketio.on('screen_ice_candidate')
    def handle_screen_ice_candidate(data):
        """Handle screen sharing ICE candidate"""
        from flask_socketio import emit
        room_id = data.get('room_id')
        candidate = data.get('candidate')

        if not room_id or not candidate:
            return

        emit('screen_ice_candidate', {
            'candidate': candidate,
            'from': room_participants.get(room_id, {}).get(request.sid)
        }, room=room_id, skip_sid=request.sid)

    @socketio.on('room_name_updated')
    def handle_room_name_updated(data):
        """Handle room name update"""
        from flask_socketio import emit
        room_id = data.get('room_id')
        room_name = data.get('room_name')

        if not room_id or not room_name:
            return

        # Broadcast to all participants in the room
        emit('room_name_changed', {
            'room_name': room_name
        }, room=room_id)

    # ===== WHITEBOARD EVENTS =====
    @socketio.on('whiteboard_draw')
    def handle_whiteboard_draw(data):
        """Handle whiteboard drawing"""
        from flask_socketio import emit
        room_id = data.get('room_id')
        stroke = data.get('stroke')

        if not room_id or not stroke:
            return

        if room_id not in room_whiteboard:
            room_whiteboard[room_id] = {'strokes': [], 'current_color': '#000000', 'current_size': 2}

        room_whiteboard[room_id]['strokes'].append(stroke)

        emit('whiteboard_draw', {
            'stroke': stroke,
            'user_name': room_participants.get(room_id, {}).get(request.sid, 'Unknown')
        }, room=room_id, skip_sid=request.sid)

    @socketio.on('whiteboard_clear')
    def handle_whiteboard_clear(data):
        """Handle whiteboard clear"""
        from flask_socketio import emit
        room_id = data.get('room_id')

        if not room_id:
            return

        if room_id in room_whiteboard:
            room_whiteboard[room_id]['strokes'] = []

        emit('whiteboard_cleared', room=room_id)

    @socketio.on('whiteboard_undo')
    def handle_whiteboard_undo(data):
        """Handle whiteboard undo"""
        from flask_socketio import emit
        room_id = data.get('room_id')

        if not room_id or room_id not in room_whiteboard:
            return

        if room_whiteboard[room_id]['strokes']:
            room_whiteboard[room_id]['strokes'].pop()

        emit('whiteboard_undone', room=room_id)

    # ===== POLL EVENTS =====
    @socketio.on('poll_create')
    def handle_poll_create(data):
        """Handle poll creation"""
        from flask_socketio import emit
        room_id = data.get('room_id')
        question = data.get('question')
        options = data.get('options')

        if not room_id or not question or not options or len(options) < 2:
            return

        if room_id not in room_polls:
            room_polls[room_id] = {}

        poll_id = str(uuid.uuid4())[:8]
        room_polls[room_id][poll_id] = {
            'question': question,
            'options': options,
            'votes': {opt: 0 for opt in options},
            'voters': [],
            'active': True,
            'created_by': room_participants.get(room_id, {}).get(request.sid, 'Unknown')
        }

        emit('poll_created', {
            'poll_id': poll_id,
            'question': question,
            'options': options,
            'votes': {opt: 0 for opt in options}
        }, room=room_id)

    @socketio.on('poll_vote')
    def handle_poll_vote(data):
        """Handle poll voting"""
        from flask_socketio import emit
        room_id = data.get('room_id')
        poll_id = data.get('poll_id')
        option = data.get('option')
        user_name = room_participants.get(room_id, {}).get(request.sid)

        if not room_id or not poll_id or not option or not user_name:
            return

        if room_id not in room_polls or poll_id not in room_polls[room_id]:
            return

        poll = room_polls[room_id][poll_id]
        if not poll['active']:
            return

        if user_name in poll['voters']:
            emit('poll_error', {'message': 'Ou deja vote!'}, room=request.sid)
            return

        if option not in poll['options']:
            return

        poll['votes'][option] += 1
        poll['voters'].append(user_name)

        emit('poll_updated', {
            'poll_id': poll_id,
            'votes': poll['votes'],
            'total_votes': len(poll['voters'])
        }, room=room_id)

    @socketio.on('poll_close')
    def handle_poll_close(data):
        """Handle poll closing"""
        from flask_socketio import emit
        room_id = data.get('room_id')
        poll_id = data.get('poll_id')

        if not room_id or not poll_id:
            return

        if room_id not in room_polls or poll_id not in room_polls[room_id]:
            return

        room_polls[room_id][poll_id]['active'] = False

        emit('poll_closed', {
            'poll_id': poll_id,
            'results': room_polls[room_id][poll_id]['votes']
        }, room=room_id)

    # ===== RAISE HAND EVENTS =====
    @socketio.on('raise_hand')
    def handle_raise_hand(data):
        """Handle raise hand"""
        from flask_socketio import emit
        room_id = data.get('room_id')
        user_name = room_participants.get(room_id, {}).get(request.sid)

        if not room_id or not user_name:
            return

        if room_id not in room_raised_hands:
            room_raised_hands[room_id] = []

        if user_name not in room_raised_hands[room_id]:
            room_raised_hands[room_id].append(user_name)

        emit('hand_raised', {
            'user_name': user_name,
            'raised_hands': room_raised_hands[room_id]
        }, room=room_id)

    @socketio.on('lower_hand')
    def handle_lower_hand(data):
        """Handle lower hand"""
        from flask_socketio import emit
        room_id = data.get('room_id')
        user_name = data.get('user_name') or room_participants.get(room_id, {}).get(request.sid)

        if not room_id or not user_name:
            return

        if room_id in room_raised_hands and user_name in room_raised_hands[room_id]:
            room_raised_hands[room_id].remove(user_name)

        emit('hand_lowered', {
            'user_name': user_name,
            'raised_hands': room_raised_hands[room_id]
        }, room=room_id)

    # ===== BREAKOUT ROOM EVENTS =====
    @socketio.on('breakout_create')
    def handle_breakout_create(data):
        """Handle breakout room creation"""
        from flask_socketio import emit
        room_id = data.get('room_id')
        rooms = data.get('rooms', [])

        if not room_id or not rooms:
            return

        if room_id not in room_breakouts:
            room_breakouts[room_id] = {'breakout_rooms': []}

        breakout_rooms = []
        for r in rooms:
            br_id = str(uuid.uuid4())[:8]
            breakout_rooms.append({
                'id': br_id,
                'name': r.get('name', f'Sal {len(breakout_rooms)+1}'),
                'participants': []
            })

        room_breakouts[room_id]['breakout_rooms'] = breakout_rooms

        emit('breakout_created', {
            'breakout_rooms': breakout_rooms
        }, room=room_id)

    @socketio.on('breakout_join')
    def handle_breakout_join(data):
        """Handle joining a breakout room"""
        from flask_socketio import emit
        room_id = data.get('room_id')
        breakout_id = data.get('breakout_id')
        user_name = room_participants.get(room_id, {}).get(request.sid)

        if not room_id or not breakout_id or not user_name:
            return

        if room_id not in room_breakouts:
            return

        # Remove user from any current breakout
        for br in room_breakouts[room_id]['breakout_rooms']:
            if user_name in br['participants']:
                br['participants'].remove(user_name)

        # Add user to new breakout
        for br in room_breakouts[room_id]['breakout_rooms']:
            if br['id'] == breakout_id:
                br['participants'].append(user_name)
                break

        emit('breakout_updated', {
            'breakout_rooms': room_breakouts[room_id]['breakout_rooms']
        }, room=room_id)

    @socketio.on('breakout_return')
    def handle_breakout_return(data):
        """Handle returning from breakout room"""
        from flask_socketio import emit
        room_id = data.get('room_id')
        user_name = room_participants.get(room_id, {}).get(request.sid)

        if not room_id or not user_name:
            return

        if room_id not in room_breakouts:
            return

        for br in room_breakouts[room_id]['breakout_rooms']:
            if user_name in br['participants']:
                br['participants'].remove(user_name)

        emit('breakout_updated', {
            'breakout_rooms': room_breakouts[room_id]['breakout_rooms']
        }, room=room_id)

    # ===== BANDWIDTH / CONNECTION QUALITY =====
    @socketio.on('connection_stats')
    def handle_connection_stats(data):
        """Handle client connection quality stats"""
        room_id = data.get('room_id')
        stats = data.get('stats', {})

        if not room_id:
            return

        # Broadcast connection quality to room (for UI indicators)
        user_name = room_participants.get(room_id, {}).get(request.sid)
        if user_name:
            emit('peer_connection_quality', {
                'user_name': user_name,
                'quality': stats.get('quality', 'unknown')
            }, room=room_id, skip_sid=request.sid)

    @socketio.on('disconnect')
    def handle_disconnect():
        """Handle user disconnecting"""
        from flask_socketio import emit
        for room_id, participants in room_participants.items():
            if request.sid in participants:
                user_name = participants[request.sid]
                del participants[request.sid]

                # Remove from active rooms
                if room_id in active_rooms and user_name in active_rooms[room_id]['participants']:
                    active_rooms[room_id]['participants'].remove(user_name)

                    # Stop screen sharing if the sharer disconnected
                    if active_rooms[room_id].get('screen_sharer') == user_name:
                        active_rooms[room_id]['is_screen_sharing'] = False
                        active_rooms[room_id]['screen_sharer'] = None
                        emit('screen_share_stopped', room=room_id)

                    # Remove from raised hands
                    if room_id in room_raised_hands and user_name in room_raised_hands[room_id]:
                        room_raised_hands[room_id].remove(user_name)
                        emit('hand_lowered', {
                            'user_name': user_name,
                            'raised_hands': room_raised_hands[room_id]
                        }, room=room_id)

                    # Remove from breakout rooms
                    if room_id in room_breakouts:
                        for br in room_breakouts[room_id]['breakout_rooms']:
                            if user_name in br['participants']:
                                br['participants'].remove(user_name)

                    # Notify others
                    emit('user_left', {
                        'user_name': user_name,
                        'participants': active_rooms[room_id]['participants']
                    }, room=room_id)

                break

def generate_room_code():
    """Generate a unique 6-character room code"""
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if not KonferansRoom.query.filter_by(room_code=code).first():
            return code

def generate_room_id():
    """Generate a unique room ID"""
    return str(uuid.uuid4())

@konferans_bp.route('/')
def index():
    """Konferans homepage"""
    return render_template('konferans/index.html')

@konferans_bp.route('/create_room', methods=['POST'])
def create_room():
    """Create a new conference room"""
    try:
        # Try JSON first, then form data
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form

        room_name = data.get('room_name', '').strip()
        creator_name = data.get('creator_name', '').strip()
        password = data.get('password', '').strip()

        if not room_name or not creator_name:
            return jsonify({'success': False, 'message': 'Non sal la ak non ou obligatwa.'})

        if len(room_name) > 100 or len(creator_name) > 100:
            return jsonify({'success': False, 'message': 'Non yo twò long.'})

        # Get user_id from session if logged in
        user_id = session.get('user_id')
        
        # If user is logged in, try to get their profile info
        if user_id:
            from app.models.user import User
            user = User.query.get(user_id)
            if user:
                # Use user's profile info if creator_name not provided
                if not creator_name:
                    creator_name = user.name or user.pseudo
                # Store creator's WhatsApp if available
                creator_whatsapp = user.whatsapp
            else:
                creator_whatsapp = None
        else:
            creator_whatsapp = None

        room_id = generate_room_id()
        room_code = generate_room_code()

        # Hash password if provided
        hashed_password = None
        if password:
            hashed_password = generate_password_hash(password)

        # Create room in database - link to user profile if logged in
        new_room = KonferansRoom(
            room_id=room_id,
            room_code=room_code,
            room_name=room_name,
            creator_name=creator_name,
            password=hashed_password,
            user_id=user_id,  # Link to User profile
            creator_whatsapp=creator_whatsapp
        )

        db.session.add(new_room)
        db.session.commit()

        # Initialize room data
        active_rooms[room_id] = {
            'participants': [],
            'is_recording': False,
            'recording_started_by': None
        }

        return jsonify({
            'success': True,
            'room_code': room_code,
            'room_id': room_id,
            'redirect': f'/konferans/room/{room_code}?user_name={creator_name}',
            'message': f'Sal {room_name} kreye avèk siksè!'
        })

    except Exception as e:
        db.session.rollback()
        print(f"Error creating room: {e}")
        return jsonify({'success': False, 'message': 'Erè nan kreasyon sal la.'})

@konferans_bp.route('/join_room', methods=['POST'])
def join_room_route():
    """Join an existing conference room"""
    try:
        # Try JSON first, then form data
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form

        room_code = data.get('room_code', '').strip().upper()
        user_name = data.get('user_name', '').strip()
        password = data.get('password', '').strip()

        if not room_code or not user_name:
            return jsonify({'success': False, 'message': 'Kòd sal la ak non ou obligatwa.'})

        # Find room
        room = KonferansRoom.query.filter_by(room_code=room_code, is_active=True).first()
        if not room:
            return jsonify({'success': False, 'message': 'Sal sa pa egziste oubyen li pa aktif.'})

        # Check password if required
        if room.password:
            if not password or not check_password_hash(room.password, password):
                return jsonify({'success': False, 'message': 'Modpas sa pa kòrèk.'})

        return jsonify({
            'success': True,
            'room_id': room.room_id,
            'room_code': room.room_code,
            'room_name': room.room_name,
            'creator_name': room.creator_name,
            'redirect': f'/konferans/room/{room.room_code}?user_name={user_name}',
            'message': f'Byenvini nan sal {room.room_name}!'
        })

    except Exception as e:
        print(f"Error joining room: {e}")
        return jsonify({'success': False, 'message': 'Erè nan antre nan sal la.'})

@konferans_bp.route('/check_room/<room_code>')
def check_room(room_code):
    """Check if room exists and if it requires password"""
    try:
        room_code = room_code.upper()
        room = KonferansRoom.query.filter_by(room_code=room_code, is_active=True).first()

        if not room:
            return jsonify({'exists': False})

        return jsonify({
            'exists': True,
            'has_password': bool(room.password)
        })

    except Exception as e:
        print(f"Error checking room: {e}")
        return jsonify({'exists': False})

@konferans_bp.route('/room/<room_code>')
def room(room_code):
    """Conference room page"""
    try:
        room_code = room_code.upper()
        room = KonferansRoom.query.filter_by(room_code=room_code, is_active=True).first()

        if not room:
            return "Sal sa pa egziste oubyen li pa aktif.", 404

        user_name = request.args.get('user_name', 'Envite')
        is_owner = user_name.lower() == room.creator_name.lower()

        return render_template('konferans/room.html',
                             room=room,
                             user_name=user_name,
                             is_owner=is_owner)

    except Exception as e:
        print(f"Error loading room: {e}")
        return "Erè nan chajman sal la.", 500

@konferans_bp.route('/upload_recording/<room_id>', methods=['POST'])
def upload_recording(room_id):
    """Upload recording file"""
    try:
        if 'recording' not in request.files:
            return jsonify({'success': False, 'message': 'Pa gen dosye anrejistreman.'})

        file = request.files['recording']
        if file.filename == '':
            return jsonify({'success': False, 'message': 'Non dosye vid.'})

        # Create recordings directory if it doesn't exist
        recordings_dir = os.path.join('static', 'recordings')
        os.makedirs(recordings_dir, exist_ok=True)

        # Generate unique filename
        filename = f"recording_{room_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.webm"
        file_path = os.path.join(recordings_dir, filename)

        # Save file
        file.save(file_path)

        # Save recording info to database
        recording = KonferansRecording(
            room_id=room_id,
            filename=filename,
            file_path=file_path,
            file_size=os.path.getsize(file_path) if os.path.exists(file_path) else None
        )

        db.session.add(recording)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Anrejistreman telechaje avèk siksè!',
            'filename': filename
        })

    except Exception as e:
        db.session.rollback()
        print(f"Error uploading recording: {e}")
        return jsonify({'success': False, 'message': 'Erè nan telechajman anrejistreman an.'})

@konferans_bp.route('/update_room_name', methods=['POST'])
def update_room_name():
    """Update room name"""
    try:
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form

        room_id = data.get('room_id')
        room_name = data.get('room_name', '').strip()

        if not room_id or not room_name:
            return jsonify({'success': False, 'message': 'ID sal la ak non sal la obligatwa.'})

        if len(room_name) > 100:
            return jsonify({'success': False, 'message': 'Non sal la twò long.'})

        room = KonferansRoom.query.filter_by(room_id=room_id).first()
        if not room:
            return jsonify({'success': False, 'message': 'Sal sa pa egziste.'})

        room.room_name = room_name
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Non sal la chanje an {room_name}!'
        })

    except Exception as e:
        db.session.rollback()
        print(f"Error updating room name: {e}")
        return jsonify({'success': False, 'message': 'Erè nan modifye non sal la.'})

@konferans_bp.route('/download_recording/<filename>')
@login_required
def download_recording(filename):
    """Download recording file — P1 FIX: login_required + safe filename + dir traversal blocked"""
    try:
        recordings_dir = os.path.abspath(os.path.join(os.getcwd(), 'static', 'recordings'))
        if not os.path.isdir(recordings_dir):
            os.makedirs(recordings_dir, exist_ok=True)
        safe = secure_filename(str(filename))
        target = safe_join(recordings_dir, safe)
        if not target or not os.path.abspath(target).startswith(recordings_dir) or not os.path.isfile(target):
            return "Dosye a pa egziste oubyen se yon operasyon enterdi.", 404
        is_admin = False
        try:
            is_admin = bool(current_user.is_authenticated and current_user.is_admin)
        except Exception:
            is_admin = False
        rec = KonferansRecording.query.filter_by(filename=safe).first()
        if rec and not is_admin:
            room = KonferansRoom.query.filter_by(room_id=rec.room_id).first() if rec.room_id else None
            is_owner = current_user.is_authenticated and room and (
                (hasattr(room, 'creator_whatsapp') and room.creator_whatsapp == current_user.whatsapp) or
                (getattr(room, 'creator_name', '') == (current_user.name or current_user.pseudo or ''))
            )
            if not is_owner:
                return "Ou pa gen dwa telechaje dosye sa a.", 403
        return send_from_directory(recordings_dir, safe, as_attachment=True)

    except Exception as e:
        print(f"Error downloading recording: {e}")
        return "Erè nan telechajman dosye a.", 500