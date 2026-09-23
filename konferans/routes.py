from flask import Blueprint, render_template, request, jsonify, session, send_from_directory, current_app, url_for
from flask_socketio import emit, join_room, leave_room
from flask_login import login_required, current_user
from app import db
from app.models import KonferansRoom, KonferansRecording, KonferansStreamSession, User
from app.utils.security import admin_required
from app.services.gkach_service import GkachService
from app.utils.validators import ValidationError
import uuid
import os
import json
import random
import string
import urllib.parse
from werkzeug.security import generate_password_hash, check_password_hash, safe_join
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import secrets

_ALLOWED_RECORDING_EXTS = {'.webm', '.mp4', '.mkv', '.mov', '.ogg', '.m4v'}
_MAX_RECORDING_MB = 512

# ===== Social-media live streaming (Facebook / YouTube / TikTok / custom RTMP) =====
_STREAM_PLATFORMS = {
    'facebook': {
        'label': 'Facebook Live',
        'ingest_hint': 'rtmps://live-api-s.facebook.com:443/rtmp/',
        'dashboard': 'https://www.facebook.com/live/producer',
        'help': 'Al sou Facebook Live Producer, kreye yon "Live video" ak "Streaming software", kopye Server URL la + Stream Key la.',
    },
    'youtube': {
        'label': 'YouTube Live',
        'ingest_hint': 'rtmp://a.rtmp.youtube.com/live2',
        'dashboard': 'https://studio.youtube.com/channel/livestreaming',
        'help': 'Nan YouTube Studio → Go Live → "Streaming software", kopye Stream URL la + Stream Key la.',
    },
    'tiktok': {
        'label': 'TikTok Live',
        'ingest_hint': 'rtmp://push.tiktokcdn.com/live',
        'dashboard': 'https://livecenter.tiktok.com/producer',
        'help': 'Nan TikTok Live Center → "Go LIVE" (atè 18 ans + / kont ki gen aksè Live), kopye Server URL la + Stream Key la.',
    },
    'whatsapp': {
        'label': 'WhatsApp (Sove Konferans)',
        'ingest_hint': '',
        'dashboard': None,
        'help': 'Anrejistre odio konferans lan epi pataje l nan WhatsApp (gade lyen telechajman an apre anrejistreman).',
    },
    'custom': {
        'label': 'RTMP Custom',
        'ingest_hint': 'rtmp://',
        'dashboard': None,
        'help': 'Antre URL RTMP(S) pwòp ou (MediaMTX, nginx-rtmp, Twitch, konfere…).',
    },
}

# Runtime state of the active live session per room (survives reconnects of
# other participants; owner re-join reads status via /api/stream/status).
# room_id: {platform, title, ingest_url, stream_key_masked, started_at: datetime, session_db_id}
room_stream_sessions = {}


def _mask_stream_key(key):
    """Mask a stream key — we only ever persist/display a masked version."""
    if not key:
        return None
    k = str(key).strip()
    if len(k) <= 4:
        return '****'
    return '*' * (len(k) - 4) + k[-4:]


def _stream_session_payload(room_id):
    """Snapshot of the current live-stream state for a room (or None)."""
    s = room_stream_sessions.get(room_id)
    if not s:
        return None
    started_at = s.get('started_at')
    elapsed = None
    if started_at:
        try:
            elapsed = max(0, int((datetime.utcnow() - started_at).total_seconds()))
        except Exception:
            elapsed = None
    return {
        'room_id': room_id,
        'platform': s.get('platform'),
        'platform_label': (_STREAM_PLATFORMS.get(s.get('platform'), {}) or {}).get('label', s.get('platform')),
        'title': s.get('title'),
        'stream_key_masked': s.get('stream_key_masked'),
        'started_at': started_at.isoformat() if started_at else None,
        'elapsed_seconds': elapsed,
        'session_id': s.get('session_db_id'),
    }


def _so_emit_stream(event, payload, room_id):
    """Broadcast a streaming event to everyone in the Socket.IO room.

    Uses the app-level SocketIO instance (HTTP routes have no socket request
    context, so flask_socketio.emit() would fail with a namespace error).
    """
    try:
        from app import socketio as _socketio
        _socketio.emit(event, payload, room=room_id, namespace='/')
    except Exception as e:
        print(f"Error broadcasting stream event '{event}': {e}")


def _stop_stream_session(room_id, reason='manual'):
    """Stop the active live session of a room (shared by HTTP stop + disconnect).

    Single source of truth so the in-RAM state, the DB row and the room
    broadcast can never drift apart — otherwise a ghost "LIVE" banner stays on
    every participant screen after the owner closes the tab.

    Returns the 'streaming_stopped' payload, or None when nothing was live.
    """
    active = room_stream_sessions.pop(room_id, None)
    if not active:
        return None

    now = datetime.utcnow()
    try:
        duration = max(0, int((now - active.get('started_at')).total_seconds()))
    except Exception:
        duration = None

    try:
        session_db_id = active.get('session_db_id')
        row = db.session.get(KonferansStreamSession, session_db_id) if session_db_id else None
        if row:
            row.status = 'stopped'
            row.stopped_at = now
            row.duration_seconds = duration
            db.session.commit()
    except Exception:
        db.session.rollback()

    payload = {
        'room_id': room_id,
        'platform': active.get('platform'),
        'title': active.get('title'),
        'duration_seconds': duration,
        'stopped_reason': reason,
    }
    _so_emit_stream('streaming_stopped', payload, room_id)
    return payload


FREE_MINUTES_DEFAULT = 45
GKACH_PER_HOUR_DEFAULT = 250
REMINDER_INTERVAL_MIN = 10

konferans_bp = Blueprint('konferans', __name__, url_prefix='/konferans', template_folder='templates')

# Global variables for room management
active_rooms = {}  # room_id: {participants: [], is_recording: False, ...}
room_participants = {}  # room_id: {socket_id: user_name}
room_whiteboard = {}  # room_id: {strokes: [], current_color: '#000000', current_size: 2}
room_polls = {}  # room_id: {poll_id: {question, options, votes, active}}
room_raised_hands = {}  # room_id: [user_name, ...]
room_breakouts = {}  # room_id: {breakout_rooms: [{id, name, participants: []}]}
room_socket_users = {}  # room_id: {socket_id: {user_name, user_id, is_owner}}
room_waiting = {}  # room_id: [{sid: str, user_name: str, ts: datetime}]
room_banned = {}  # room_id: set[str] of banned user_names
room_admitted = {}  # room_id: set[str] of user_names already admitted via the waiting room


def _broadcast_locks(room_id, room=None):
    """Build & emit current mic/cam/chat/class + waiting room state for a room."""
    from flask_socketio import emit as _so_emit
    locks = {
        'mic_locked': False,
        'cam_locked': False,
        'chat_locked': False,
        'class_locked': False,
        'waiting_room': bool(active_rooms.get(room_id, {}).get('waiting_room')),
        'room_locked': bool(active_rooms.get(room_id, {}).get('room_locked')),
    }
    try:
        if room is None:
            room = KonferansRoom.query.filter_by(room_id=room_id, is_active=True).first()
        if room:
            locks['mic_locked'] = bool(getattr(room, 'mic_locked', False))
            locks['cam_locked'] = bool(getattr(room, 'cam_locked', False))
            locks['chat_locked'] = bool(getattr(room, 'chat_locked', False))
            locks['class_locked'] = bool(getattr(room, 'class_locked', False))
    except Exception:
        pass
    _so_emit('room_locks_updated', locks, room=room_id)
    return locks


def _broadcast_participants(room_id):
    """Re-emit the full participants list with sid + ownership info (for UI moderation menus)."""
    from flask_socketio import emit as _so_emit
    info = []
    for sid, name in room_participants.get(room_id, {}).items():
        ident = room_socket_users.get(room_id, {}).get(sid, {})
        info.append({
            'sid': sid,
            'user_name': name,
            'is_owner': bool(ident.get('is_owner')),
            'user_id': ident.get('user_id'),
        })
    _so_emit('participants_info', {'list': info}, room=room_id)


def _broadcast_waiting(room_id):
    from flask_socketio import emit as _so_emit
    waiting = room_waiting.get(room_id, [])
    clean = []
    for w in waiting:
        ts = w.get('ts')
        try:
            ts_iso = ts.isoformat() if ts else None
        except Exception:
            ts_iso = None
        clean.append({
            'sid': w.get('sid'),
            'user_name': w.get('user_name'),
            'ts': ts_iso,
        })
    _so_emit('waiting_list_updated', {'count': len(clean), 'list': clean}, room=room_id)


def _socket_member(room_id, sid):
    """Return the authenticated socket identity only if it joined this room."""
    return room_socket_users.get(room_id, {}).get(sid)


def _socket_owner(room_id, sid):
    identity = _socket_member(room_id, sid)
    return bool(identity and identity.get('is_owner'))


def _room_owner(room):
    return bool(
        room and current_user.is_authenticated and room.user_id
        and int(room.user_id) == int(current_user.id)
    )

def register_socketio_handlers(socketio):
    """Register all socketio event handlers"""
    
    @socketio.on('join')
    def handle_join(data):
        """Handle user joining a room — checks ban list, waiting room state, locks."""
        from flask_socketio import join_room, emit
        room_id = data.get('room_id')
        user_name = data.get('user_name')

        if not room_id or not user_name:
            return

        # Get room from database to check max participants
        room = KonferansRoom.query.filter_by(room_id=room_id, is_active=True).first()
        if not room:
            emit('join_error', {'message': 'Sal sa pa egziste oubyen li pa aktif.'}, room=request.sid)
            return

        # --- BAN LIST CHECK ---
        if user_name in room_banned.get(room_id, set()):
            emit('join_error', {
                'message': 'Ou te retire de sal la. Kontakte pwopriyetè a si ou vle antre.'
            }, room=request.sid)
            return

        # --- OWNER STATUS ---
        is_owner_call = _room_owner(room)

        # --- ROOM LOCKED / WAITING ROOM CHECK (owner + admin always bypass) ---
        is_super_admin = False
        try:
            if current_user.is_authenticated and bool(getattr(current_user, 'is_admin', False)):
                is_super_admin = True
        except Exception:
            is_super_admin = False
        can_bypass = is_owner_call or is_super_admin

        # --- PASSWORD GATE (owner + admin bypass; flag set by the /room page) ---
        if room.password and not can_bypass:
            if not session.get(f'konf_pw_ok_{room.room_id}'):
                emit('join_error', {
                    'message': 'Sal sa pwoteje ak yon modpas. Tanpri antre atravè paj sal la.'
                }, room=request.sid)
                return

        use_waiting = bool(active_rooms.get(room_id, {}).get('waiting_room'))
        room_locked = bool(active_rooms.get(room_id, {}).get('room_locked'))

        # Users already admitted once skip re-queueing (the admission_granted
        # handler reloads the page, which re-emits 'join').
        already_admitted = user_name in room_admitted.get(room_id, set())

        if not can_bypass:
            if room_locked and use_waiting and not already_admitted:
                # Do NOT join the SocketIO room — keep the waiting list in RAM
                room_waiting.setdefault(room_id, [])
                # Avoid duplicates for same sid
                room_waiting[room_id] = [w for w in room_waiting[room_id] if w.get('sid') != request.sid]
                room_waiting[room_id].append({
                    'sid': request.sid,
                    'user_name': user_name,
                    'ts': datetime.now(),
                })
                emit('admission_required', {
                    'message': 'Nap tann pwomotè a otorize ou antre nan sal la...',
                    'room_name': getattr(room, 'room_name', '')
                }, room=request.sid)
                _broadcast_waiting(room_id)
                return

            if room_locked and not use_waiting:
                count_now = len(active_rooms.get(room_id, {}).get('participants', []))
                if count_now >= 1:
                    emit('join_error', {
                        'message': 'Sal la fèmen kounye a. Tanpri kontakte pwopriyetè a.'
                    }, room=request.sid)
                    return

        # Enforce max_participants ceiling BEFORE allowing join
        try:
            max_p = int(getattr(room, 'max_participants', 50) or 50)
        except (TypeError, ValueError):
            max_p = 50
        current_count = len(active_rooms.get(room_id, {}).get('participants', []))
        if current_count >= max_p and not can_bypass:
            emit('join_error', {
                'message': 'Sal la deja koupli (max {} patisipan). Tanpri eseye ankò pita oubyen kontakte pwopriyetè a.'.format(max_p)
            }, room=request.sid)
            return

        from flask_socketio import join_room as _jr2, emit as _e2
        _jr2(room_id)

        # Add participant to room
        if room_id not in active_rooms:
            active_rooms[room_id] = {
                'participants': [],
                'is_recording': False,
                'recording_started_by': None,
                'is_screen_sharing': False,
                'screen_sharer': None,
                'waiting_room': False,
                'room_locked': False,
            }

        if user_name not in active_rooms[room_id]['participants']:
            active_rooms[room_id]['participants'].append(user_name)

        room_participants[room_id] = room_participants.get(room_id, {})
        room_participants[room_id][request.sid] = user_name
        room_socket_users[room_id] = room_socket_users.get(room_id, {})
        room_socket_users[room_id][request.sid] = {
            'user_name': user_name,
            'user_id': current_user.id if current_user.is_authenticated else None,
            'is_owner': _room_owner(room),
        }

        # Get list of other participants
        peers = []
        for sid, name in room_participants[room_id].items():
            if sid != request.sid:
                peers.append({'sid': sid, 'user_name': name})

        # Send existing peers + room locks + current waiting count to the new user
        emit('all_users', peers, room=request.sid)
        locks_now = {
            'mic_locked': bool(getattr(room, 'mic_locked', False)),
            'cam_locked': bool(getattr(room, 'cam_locked', False)),
            'chat_locked': bool(getattr(room, 'chat_locked', False)),
            'class_locked': bool(getattr(room, 'class_locked', False)),
            'waiting_room': bool(active_rooms[room_id].get('waiting_room')),
            'room_locked': bool(active_rooms[room_id].get('room_locked')),
        }
        emit('room_locks_updated', locks_now, room=request.sid)

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

        # Re-broadcast enriched participant info + waiting list (for owner UI refresh)
        _broadcast_participants(room_id)
        if is_owner_call or is_super_admin:
            _broadcast_waiting(room_id)

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
        identity = _socket_member(room_id, request.sid)
        user_name = identity.get('user_name') if identity else None

        if not room_id or not message or not user_name:
            return

        if len(message) > 500:  # Limit message length
            return

        # Enforce the owner's chat lock server-side (owner exempt)
        if not identity.get('is_owner'):
            chat_locked = False
            try:
                room_row = KonferansRoom.query.filter_by(room_id=room_id, is_active=True).first()
                chat_locked = bool(getattr(room_row, 'chat_locked', False)) if room_row else False
            except Exception:
                chat_locked = False
            if chat_locked:
                emit('chat_rejected', {
                    'message': 'Chat la fèmen pa pwomotè a.'
                }, room=request.sid)
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

        if not room_id or room_id not in active_rooms or not _socket_owner(room_id, request.sid):
            return

        active_rooms[room_id]['is_recording'] = True
        active_rooms[room_id]['recording_started_by'] = room_participants.get(room_id, {}).get(request.sid)

        emit('recording_started', room=room_id)

    @socketio.on('stop_recording')
    def handle_stop_recording(data):
        """Handle recording stop"""
        from flask_socketio import emit
        room_id = data.get('room_id')

        if not room_id or room_id not in active_rooms or not _socket_owner(room_id, request.sid):
            return

        active_rooms[room_id]['is_recording'] = False
        active_rooms[room_id]['recording_started_by'] = None

        emit('recording_stopped', room=room_id)

    @socketio.on('start_screen_share')
    def handle_start_screen_share(data):
        """Handle screen sharing start"""
        from flask_socketio import emit
        room_id = data.get('room_id')

        if not room_id or room_id not in active_rooms or not _socket_member(room_id, request.sid):
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

        if not room_id or room_id not in active_rooms or not _socket_member(room_id, request.sid):
            return

        active_rooms[room_id]['is_screen_sharing'] = False
        active_rooms[room_id]['screen_sharer'] = None

        emit('screen_share_stopped', room=room_id)

    @socketio.on('share_media')
    def handle_share_media(data):
        """Handle media sharing — broadcast to room for display in main window or chat"""
        from flask_socketio import emit
        room_id = data.get('room_id')
        identity = _socket_member(room_id, request.sid)
        user_name = identity.get('user_name') if identity else None
        media_url = data.get('media_url')
        media_type = data.get('media_type', 'image')
        display_mode = data.get('display_mode', 'main')  # 'main' or 'chat'
        original_name = data.get('original_name', '')

        if not room_id or not media_url or not user_name:
            return

        # Broadcast media to room (including sender for confirmation)
        emit('media_shared', {
            'user_name': user_name,
            'url': media_url,
            'media_url': media_url,
            'media_type': media_type,
            'display_mode': display_mode,
            'original_name': original_name,
            'timestamp': datetime.now().strftime('%H:%M')
        }, room=room_id)

    @socketio.on('screen_offer')
    def handle_screen_offer(data):
        """Handle screen sharing offer"""
        from flask_socketio import emit
        room_id = data.get('room_id')
        offer = data.get('offer')

        if not room_id or not offer or not _socket_member(room_id, request.sid):
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

        if not room_id or not answer or not _socket_member(room_id, request.sid):
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

        if not room_id or not candidate or not _socket_member(room_id, request.sid):
            return

        emit('screen_ice_candidate', {
            'candidate': candidate,
            'from': room_participants.get(room_id, {}).get(request.sid)
        }, room=room_id, skip_sid=request.sid)

    @socketio.on('room_name_updated')
    def handle_room_name_updated(data):
        """Handle room name update — persist to DB ONLY when requester is owner, then broadcast"""
        from flask_socketio import emit
        room_id = data.get('room_id')
        room_name = (data.get('room_name') or '').strip()

        if not room_id or not room_name:
            return

        # Load room and validate ownership from the authenticated socket identity.
        room = KonferansRoom.query.filter_by(room_id=room_id, is_active=True).first()
        if room and _socket_owner(room_id, request.sid):
            try:
                if len(room_name) > 120:
                    room_name = room_name[:120]
                room.room_name = room_name
                db.session.commit()
            except Exception:
                db.session.rollback()
        elif not _socket_member(room_id, request.sid):
            return

        # Broadcast to all participants in the room (even if persist skipped, reflect in-session)
        emit('room_name_changed', {
            'room_id': room_id,
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

    # ===== MEDIA ANNOTATION EVENTS (Selection Pen / Highlighter for teacher-uploaded media) =====
    @socketio.on('media_annotation')
    def handle_media_annotation(data):
        """Broadcast a pen/highlight/rect/arrow annotation drawn on shared media (owner-only write)."""
        from flask_socketio import emit
        room_id = data.get('room_id')
        stroke = data.get('stroke')
        user_name = data.get('user_name') or room_participants.get(room_id, {}).get(request.sid, 'Unknown')

        if not room_id or not stroke:
            return
        # Only owner socket identity may originate new annotation strokes (broadcast rest to room)
        if not _socket_owner(room_id, request.sid):
            return

        emit('media_annotation', {
            'stroke': stroke,
            'user_name': user_name,
        }, room=room_id)

    @socketio.on('media_annotation_undo')
    def handle_media_annotation_undo(data):
        """Owner requested undo — broadcast a pop instruction to all clients."""
        from flask_socketio import emit
        room_id = data.get('room_id')
        if not room_id or not _socket_owner(room_id, request.sid):
            return
        emit('media_annotation_undo', {
            'removed_ts': data.get('removed_ts'),
        }, room=room_id)

    @socketio.on('media_annotation_clear')
    def handle_media_annotation_clear(data):
        """Owner requested erase-all — broadcast clear to all clients."""
        from flask_socketio import emit
        room_id = data.get('room_id')
        if not room_id or not _socket_owner(room_id, request.sid):
            return
        emit('media_annotation_clear', room=room_id)

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

    # ===== MODERATION: Kick / Mute-Remote / Lock / Unlock =====
    @socketio.on('kick_participant')
    def handle_kick_participant(data):
        """Owner / Admin kicks + optionally bans a participant by SID."""
        from flask_socketio import emit
        room_id = data.get('room_id')
        target_sid = data.get('target_sid')
        do_ban = bool(data.get('ban'))
        if not room_id or not target_sid:
            return
        if not _socket_owner(room_id, request.sid):
            try:
                is_admin = current_user.is_authenticated and bool(getattr(current_user, 'is_admin', False))
            except Exception:
                is_admin = False
            if not is_admin:
                return

        target_name = room_participants.get(room_id, {}).get(target_sid)
        if not target_name:
            return

        # Optional: ban in memory
        if do_ban:
            room_banned.setdefault(room_id, set())
            room_banned[room_id].add(target_name)

        # Tell target they are being removed
        emit('user_kicked', {
            'room_id': room_id,
            'reason': data.get('reason') or 'Yo retire ou nan sal la.'
        }, room=target_sid)

        # Broadcast to room
        emit('participant_removed', {
            'sid': target_sid,
            'user_name': target_name,
            'banned': do_ban,
            'by': room_participants.get(room_id, {}).get(request.sid, 'Admin'),
        }, room=room_id, skip_sid=target_sid)

        # Force SocketIO leave + prune state (mimics disconnect)
        try:
            from flask_socketio import leave_room as _so_leave
            _so_leave(room_id, sid=target_sid)
        except Exception:
            pass
        room_participants.get(room_id, {}).pop(target_sid, None)
        room_socket_users.get(room_id, {}).pop(target_sid, None)
        if room_id in active_rooms and target_name in active_rooms[room_id]['participants']:
            # Only remove from participants list if it was that sid's name (handle duplicates cautiously)
            names_left = list(room_participants.get(room_id, {}).values())
            if target_name not in names_left:
                active_rooms[room_id]['participants'].remove(target_name)
        _broadcast_participants(room_id)

    @socketio.on('mute_remote_audio')
    def handle_mute_remote_audio(data):
        from flask_socketio import emit
        room_id = data.get('room_id')
        target_sid = data.get('target_sid')
        if not room_id or not target_sid or not _socket_owner(room_id, request.sid):
            return
        emit('mute_audio_requested', {
            'sid': target_sid,
            'by': room_participants.get(room_id, {}).get(request.sid, 'Admin')
        }, room=target_sid)
        target_name = room_participants.get(room_id, {}).get(target_sid)
        emit('mute_notice', {
            'who': target_name, 'track': 'audio',
            'by': room_participants.get(room_id, {}).get(request.sid, 'Admin')
        }, room=room_id, skip_sid=target_sid)

    @socketio.on('mute_remote_video')
    def handle_mute_remote_video(data):
        from flask_socketio import emit
        room_id = data.get('room_id')
        target_sid = data.get('target_sid')
        if not room_id or not target_sid or not _socket_owner(room_id, request.sid):
            return
        emit('mute_video_requested', {
            'sid': target_sid,
            'by': room_participants.get(room_id, {}).get(request.sid, 'Admin')
        }, room=target_sid)
        target_name = room_participants.get(room_id, {}).get(target_sid)
        emit('mute_notice', {
            'who': target_name, 'track': 'video',
            'by': room_participants.get(room_id, {}).get(request.sid, 'Admin')
        }, room=room_id, skip_sid=target_sid)

    @socketio.on('update_room_locks')
    def handle_update_room_locks(data):
        """Owner toggles mic/cam/chat locked, waiting room, or room entry lock — persists DB where possible + emits."""
        from flask_socketio import emit
        room_id = data.get('room_id')
        if not room_id or not _socket_owner(room_id, request.sid):
            return

        active_rooms.setdefault(room_id, {
            'participants': [],
            'is_recording': False,
            'recording_started_by': None,
            'is_screen_sharing': False,
            'screen_sharer': None,
            'waiting_room': False,
            'room_locked': False,
        })
        ar = active_rooms[room_id]

        # RAM-first toggles
        for key in ('waiting_room', 'room_locked'):
            if key in data:
                try:
                    ar[key] = bool(data[key])
                except (TypeError, ValueError):
                    pass

        # DB-persisted columns (mic/cam/chat/class locked)
        room_row = KonferansRoom.query.filter_by(room_id=room_id, is_active=True).first()
        if room_row:
            changed = False
            for col in ('mic_locked', 'cam_locked', 'chat_locked', 'class_locked'):
                if col in data:
                    v = bool(data[col])
                    if getattr(room_row, col, None) != v:
                        try:
                            setattr(room_row, col, v)
                            changed = True
                        except Exception:
                            pass
            if changed:
                try:
                    db.session.commit()
                except Exception:
                    db.session.rollback()

        # Force apply mic/cam lock to all participants right now
        if room_row and getattr(room_row, 'mic_locked', False):
            for sid in list(room_participants.get(room_id, {}).keys()):
                if sid != request.sid and not _socket_owner(room_id, sid):
                    try:
                        emit('mute_audio_requested', {
                            'sid': sid,
                            'by': getattr(room_row, 'creator_name', 'Pwomotè')
                        }, room=sid)
                    except Exception:
                        pass
        if room_row and getattr(room_row, 'cam_locked', False):
            for sid in list(room_participants.get(room_id, {}).keys()):
                if sid != request.sid and not _socket_owner(room_id, sid):
                    try:
                        emit('mute_video_requested', {
                            'sid': sid,
                            'by': getattr(room_row, 'creator_name', 'Pwomotè')
                        }, room=sid)
                    except Exception:
                        pass

        # Broadcast final state to the whole room (single emit — _broadcast_locks already targets the room)
        _broadcast_locks(room_id, room=room_row)

    # ===== WAITING ROOM: admission controls =====
    @socketio.on('admit_user')
    def handle_admit_user(data):
        from flask_socketio import join_room as _jr, emit as _e
        room_id = data.get('room_id')
        target_sid = data.get('target_sid')
        if not room_id or not target_sid or not _socket_owner(room_id, request.sid):
            return
        waiting = room_waiting.get(room_id, [])
        entry = next((w for w in waiting if w.get('sid') == target_sid), None)
        if not entry:
            return
        waiting.remove(entry)
        user_name = entry['user_name']
        # Remember the admission so the post-admission page reload skips the queue
        room_admitted.setdefault(room_id, set()).add(user_name)

        room_row = KonferansRoom.query.filter_by(room_id=room_id, is_active=True).first()
        try:
            _jr(room_id, sid=target_sid)
        except Exception:
            pass

        # Attach participant state (mirrors handle_join)
        active_rooms.setdefault(room_id, {
            'participants': [], 'is_recording': False,
            'recording_started_by': None, 'is_screen_sharing': False,
            'screen_sharer': None, 'waiting_room': False, 'room_locked': False,
        })
        if user_name not in active_rooms[room_id]['participants']:
            active_rooms[room_id]['participants'].append(user_name)
        room_participants.setdefault(room_id, {})
        room_participants[room_id][target_sid] = user_name
        room_socket_users.setdefault(room_id, {})
        room_socket_users[room_id][target_sid] = {
            'user_name': user_name, 'user_id': None, 'is_owner': False,
        }

        peers = []
        for sid, nm in room_participants[room_id].items():
            if sid != target_sid:
                peers.append({'sid': sid, 'user_name': nm})

        _e('all_users', peers, room=target_sid)
        locks = {
            'mic_locked': bool(getattr(room_row, 'mic_locked', False)),
            'cam_locked': bool(getattr(room_row, 'cam_locked', False)),
            'chat_locked': bool(getattr(room_row, 'chat_locked', False)),
            'class_locked': bool(getattr(room_row, 'class_locked', False)),
            'waiting_room': bool(active_rooms[room_id].get('waiting_room')),
            'room_locked': bool(active_rooms[room_id].get('room_locked')),
        }
        _e('room_locks_updated', locks, room=target_sid)
        _e('admission_granted', {'message': 'Ou otorize! Antre nan sal la...'}, room=target_sid)

        # If mic/cam locked, force mute on admitted user immediately
        if locks['mic_locked']:
            try:
                _e('mute_audio_requested', {'sid': target_sid, 'by': 'Pwomotè'}, room=target_sid)
            except Exception:
                pass
        if locks['cam_locked']:
            try:
                _e('mute_video_requested', {'sid': target_sid, 'by': 'Pwomotè'}, room=target_sid)
            except Exception:
                pass

        # Notify existing participants
        _e('user_joined', {
            'sid': target_sid,
            'user_name': user_name,
            'participants': active_rooms[room_id]['participants'],
        }, room=room_id, skip_sid=target_sid)

        _broadcast_participants(room_id)
        _broadcast_waiting(room_id)

    @socketio.on('reject_user')
    def handle_reject_user(data):
        from flask_socketio import emit
        room_id = data.get('room_id')
        target_sid = data.get('target_sid')
        if not room_id or not target_sid or not _socket_owner(room_id, request.sid):
            return
        waiting = room_waiting.get(room_id, [])
        entry = next((w for w in waiting if w.get('sid') == target_sid), None)
        if not entry:
            return
        waiting.remove(entry)
        emit('admission_rejected', {
            'message': data.get('reason') or 'Pwomotè a pa aksepte ou antre nan sal la kounye a.'
        }, room=target_sid)
        _broadcast_waiting(room_id)

    @socketio.on('admit_all_waiting')
    def handle_admit_all_waiting(data):
        from flask_socketio import join_room as _jr, emit as _e
        room_id = data.get('room_id')
        if not room_id or not _socket_owner(room_id, request.sid):
            return
        waiting = list(room_waiting.get(room_id, []))
        for entry in waiting:
            target_sid = entry['sid']
            user_name = entry['user_name']
            room_admitted.setdefault(room_id, set()).add(user_name)
            try:
                _jr(room_id, sid=target_sid)
            except Exception:
                pass
            active_rooms.setdefault(room_id, {
                'participants': [], 'is_recording': False,
                'recording_started_by': None, 'is_screen_sharing': False,
                'screen_sharer': None, 'waiting_room': False, 'room_locked': False,
            })
            if user_name not in active_rooms[room_id]['participants']:
                active_rooms[room_id]['participants'].append(user_name)
            room_participants.setdefault(room_id, {})
            room_participants[room_id][target_sid] = user_name
            room_socket_users.setdefault(room_id, {})
            room_socket_users[room_id][target_sid] = {
                'user_name': user_name, 'user_id': None, 'is_owner': False,
            }
            peers = [{'sid': sid, 'user_name': nm} for sid, nm in room_participants[room_id].items() if sid != target_sid]
            _e('all_users', peers, room=target_sid)
            _e('admission_granted', {'message': 'Ou otorize! Antre nan sal la...'}, room=target_sid)
            _e('user_joined', {
                'sid': target_sid, 'user_name': user_name,
                'participants': active_rooms[room_id]['participants'],
            }, room=room_id, skip_sid=target_sid)
        room_waiting[room_id] = []
        _broadcast_participants(room_id)
        _broadcast_waiting(room_id)

    # ===== BANDWIDTH / CONNECTION QUALITY =====
    @socketio.on('connection_stats')
    def handle_connection_stats(data):
        """Handle client connection quality stats"""
        room_id = data.get('room_id')
        stats = data.get('stats', {})

        if not room_id or not _socket_member(room_id, request.sid):
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
                # Capture identity BEFORE popping: needed to auto-close a live session
                _identity = room_socket_users.get(room_id, {}).pop(request.sid, None) or {}
                was_owner = bool(_identity.get('is_owner'))

                # Explicitly leave the SocketIO room to avoid ghost SID accumulation
                try:
                    from flask_socketio import leave_room as _so_leave_room
                    _so_leave_room(room_id)
                except Exception:
                    pass

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

                    # Notify others (sid lets clients destroy the peer + video tile)
                    emit('user_left', {
                        'sid': request.sid,
                        'user_name': user_name,
                        'participants': active_rooms[room_id]['participants']
                    }, room=room_id)

                # Auto-close a live session: the owner's browser IS the media
                # source of the broadcast, and an empty room has nobody left to
                # watch it. Without this the RAM state + DB row stay 'live'
                # forever and every participant keeps a ghost LIVE banner.
                if room_id in room_stream_sessions and (was_owner or not participants):
                    _stop_stream_session(
                        room_id,
                        'owner_disconnect' if was_owner else 'room_empty'
                    )

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
    """Konferans homepage — includes BBC-style media showcase for recordings & uploaded media."""
    showcase_media = []

    try:
        recordings = (
            KonferansRecording.query
            .order_by(KonferansRecording.created_at.desc())
            .limit(12)
            .all()
        )
        for rec in recordings:
            room = KonferansRoom.query.filter_by(room_id=rec.room_id).first()
            ext = os.path.splitext(rec.filename)[1].lower()
            if ext in {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp', '.ico'}:
                mtype = 'image'
            elif ext in {'.mp4', '.webm', '.mov', '.m4v', '.avi', '.mkv'}:
                mtype = 'video'
            elif ext in {'.mp3', '.wav', '.ogg', '.m4a', '.flac', '.aac'}:
                mtype = 'audio'
            else:
                mtype = 'document'
            showcase_media.append({
                'type': mtype,
                'title': getattr(rec, 'title', None) or (room.room_name if room else 'Konferans'),
                'url': url_for('static', filename=f'recordings/{rec.filename}'),
                'description': room.creator_name if room else 'Enrejistreman',
                'room_name': room.room_name if room else None,
                'created_at': rec.created_at.isoformat() if getattr(rec, 'created_at', None) else None,
                'file_size': rec.file_size,
            })
    except Exception as e:
        print(f"[konferans/index] recordings scan error: {e}")

    try:
        media_dir = os.path.abspath(os.path.join(os.getcwd(), 'static', 'uploads', 'konferans'))
        if os.path.isdir(media_dir):
            files = []
            for fn in os.listdir(media_dir)[:30]:
                fp = os.path.join(media_dir, fn)
                if not os.path.isfile(fp):
                    continue
                try:
                    st = os.stat(fp)
                except OSError:
                    continue
                files.append((fn, st.st_mtime, st.st_size))
            files.sort(key=lambda x: x[1], reverse=True)
            for fn, mt, sz in files[:12]:
                ext = os.path.splitext(fn)[1].lower()
                if ext in {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp', '.ico'}:
                    mtype = 'image'
                elif ext in {'.mp4', '.webm', '.mov', '.m4v', '.avi', '.mkv'}:
                    mtype = 'video'
                elif ext in {'.mp3', '.wav', '.ogg', '.m4a', '.flac', '.aac'}:
                    mtype = 'audio'
                else:
                    mtype = 'document'
                showcase_media.append({
                    'type': mtype,
                    'title': os.path.splitext(fn)[0].split('_', 1)[-1][:60] or 'Medya',
                    'url': url_for('static', filename=f'uploads/konferans/{fn}'),
                    'description': 'Medya pataje nan Konferans',
                    'room_name': None,
                    'created_at': datetime.fromtimestamp(mt).isoformat(),
                    'file_size': sz,
                })
    except Exception as e:
        print(f"[konferans/index] uploads scan error: {e}")

    showcase_media = showcase_media[:16]

    return render_template(
        'konferans/index.html',
        showcase_media=showcase_media,
    )

@konferans_bp.route('/create_room', methods=['POST'])
@login_required
def create_room():
    """Create a new conference room.

    ONLY authenticated users can create rooms.
    creator_name / user_id / creator_whatsapp are ENFORCED from current_user
    (never trust client-supplied identity — prevents spoofing room ownership).
    """
    try:
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form

        room_name = (data.get('room_name') or '').strip()
        password = (data.get('password') or '').strip()

        if not room_name:
            return jsonify({'success': False, 'error': 'Non sal la obligatwa.'}), 400
        if len(room_name) > 100:
            return jsonify({'success': False, 'error': 'Non sal la twò long (max 100 karaktè).'}), 400

        creator_name = (current_user.name or current_user.pseudo or f"User{current_user.id}").strip()[:100]
        creator_whatsapp = getattr(current_user, 'whatsapp', None)

        room_id = generate_room_id()
        room_code = generate_room_code()

        hashed_password = None
        if password:
            if len(password) > 128:
                return jsonify({'success': False, 'error': 'Modpas la twò long.'}), 400
            hashed_password = generate_password_hash(password)

        new_room = KonferansRoom(
            room_id=room_id,
            room_code=room_code,
            room_name=room_name,
            creator_name=creator_name,
            password=hashed_password,
            user_id=current_user.id,
            creator_whatsapp=creator_whatsapp,
            is_active=True,
            started_at=datetime.utcnow(),
            room_type='classic',
            max_participants=50,
        )

        db.session.add(new_room)
        db.session.commit()

        active_rooms[room_id] = {
            'participants': [],
            'is_recording': False,
            'recording_started_by': None,
            'billing': {
                'gkach_charged_total': 0,
                'last_reminder_minutes': 0,
                'free_minutes': FREE_MINUTES_DEFAULT,
                'gkach_per_hour': GKACH_PER_HOUR_DEFAULT,
                'credit_bought_minutes': 0,
                'last_charge_minute': FREE_MINUTES_DEFAULT,
            }
        }

        base_url = request.host_url.rstrip('/')
        join_link = f"{base_url}/konferans/room/{room_code}?user_name={urllib.parse.quote(creator_name)}"

        return jsonify({
            'success': True,
            'room_code': room_code,
            'room_id': room_id,
            'redirect': f'/konferans/room/{room_code}?user_name={urllib.parse.quote(creator_name)}',
            'message': f'Sal {room_name} kreye avèk siksè!',
            'join_link': join_link,
            'invite_code': room_code,
            'billing': {
                'free_minutes': FREE_MINUTES_DEFAULT,
                'gkach_per_hour': GKACH_PER_HOUR_DEFAULT,
                'reminder_every_min': REMINDER_INTERVAL_MIN,
            }
        })

    except Exception as e:
        db.session.rollback()
        print(f"Error creating room: {e}")
        return jsonify({'success': False, 'error': 'Erè nan kreasyon sal la.'}), 500

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
            return jsonify({'success': False, 'message': 'Kòd sal la ak non ou obligatwa.'}), 400

        room = KonferansRoom.query.filter_by(room_code=room_code, is_active=True).first()
        if not room:
            return jsonify({'success': False, 'message': 'Sal sa pa egziste oubyen li pa aktif.'}), 404

        if room.password:
            if not password or not check_password_hash(room.password, password):
                return jsonify({'success': False, 'message': 'Modpas sa pa kòrèk.'}), 403
            # Remember the validation so the /room page lets the user straight in
            session[f'konf_pw_ok_{room.room_id}'] = True

        return jsonify({
            'success': True,
            'room_id': room.room_id,
            'room_code': room.room_code,
            'room_name': room.room_name,
            'creator_name': room.creator_name,
            'redirect': f'/konferans/room/{room.room_code}?user_name={urllib.parse.quote(user_name)}',
            'message': f'Byenvini nan sal {room.room_name}!'
        })

    except Exception as e:
        print(f"Error joining room: {e}")
        return jsonify({'success': False, 'message': 'Erè nan antre nan sal la.'}), 500

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

@konferans_bp.route('/room/<room_code>', methods=['GET', 'POST'])
def room(room_code):
    """Conference room page"""
    try:
        room_code = room_code.upper()
        room = KonferansRoom.query.filter_by(room_code=room_code, is_active=True).first()

        if not room:
            return "Sal sa pa egziste oubyen li pa aktif.", 404

        user_name = request.args.get('user_name') or request.form.get('user_name') or 'Envite'

        # Owner status must come from the authenticated account, never a name.
        is_owner = _room_owner(room)

        # PASSWORD GATE: a room with a password must be proven before the room
        # page is served (owner + admin bypass). The session flag is what the
        # Socket.IO 'join' handler also checks — direct links can no longer
        # bypass the password.
        if room.password and not is_owner:
            is_admin = False
            try:
                is_admin = bool(current_user.is_authenticated and getattr(current_user, 'is_admin', False))
            except Exception:
                is_admin = False
            pw_key = f'konf_pw_ok_{room.room_id}'
            if not is_admin and not session.get(pw_key):
                error = None
                status = 200
                if request.method == 'POST':
                    supplied = (request.form.get('password') or '').strip()
                    if supplied and check_password_hash(room.password, supplied):
                        session[pw_key] = True
                    else:
                        error = 'Modpas sa pa kòrèk.'
                        status = 403
                if not session.get(pw_key):
                    return render_template(
                        'konferans/room_password.html',
                        room=room,
                        user_name=user_name,
                        error=error,
                    ), status

        # Initialize started_at on first owner join (backfill for legacy rooms)
        if is_owner and not room.started_at:
            room.started_at = datetime.utcnow()
            db.session.commit()

        base_url = request.host_url.rstrip('/')
        join_link = f"{base_url}/konferans/room/{room.room_code}"

        # Compute elapsed + billing state for owner UI
        billing_info = None
        if is_owner and room.started_at:
            now = datetime.utcnow()
            elapsed_sec = max(0, int((now - room.started_at).total_seconds()))
            billing_info = {
                'elapsed_seconds': elapsed_sec,
                'free_minutes': FREE_MINUTES_DEFAULT,
                'gkach_per_hour': GKACH_PER_HOUR_DEFAULT,
                'reminder_every_min': REMINDER_INTERVAL_MIN,
            }
            try:
                if current_user.is_authenticated and getattr(current_user, 'whatsapp', None):
                    billing_info['owner_balance'] = int(GkachService.get_balance(current_user.whatsapp) or 0)
                else:
                    billing_info['owner_balance'] = 0
            except Exception:
                billing_info['owner_balance'] = 0

            if room_id_key := room.room_id:
                if room_id_key not in active_rooms:
                    active_rooms[room_id_key] = {'participants': [], 'is_recording': False, 'recording_started_by': None}
                if 'billing' not in active_rooms[room_id_key]:
                    active_rooms[room_id_key]['billing'] = {
                        'gkach_charged_total': 0,
                        'last_reminder_minutes': 0,
                        'free_minutes': FREE_MINUTES_DEFAULT,
                        'gkach_per_hour': GKACH_PER_HOUR_DEFAULT,
                        'credit_bought_minutes': 0,
                        'last_charge_minute': FREE_MINUTES_DEFAULT,
                    }

        return render_template('konferans/room.html',
                             room=room,
                             user_name=user_name,
                             is_owner=is_owner,
                             join_link=join_link,
                             billing_info=billing_info,
                             free_minutes=FREE_MINUTES_DEFAULT,
                             gkach_per_hour=GKACH_PER_HOUR_DEFAULT,
                             reminder_every_min=REMINDER_INTERVAL_MIN)

    except Exception as e:
        print(f"Error loading room: {e}")
        return "Erè nan chajman sal la.", 500


@konferans_bp.route('/api/billing/<room_id>', methods=['GET'])
@login_required
def get_billing_state(room_id):
    """Get current billing state for an owned conference room"""
    try:
        room = KonferansRoom.query.filter_by(room_id=room_id, is_active=True).first()
        if not room:
            return jsonify({'success': False, 'error': 'Sal sa pa egziste.'}), 404

        if not _room_owner(room):
            return jsonify({'success': False, 'error': 'Se sèl pwopriyetè sal la ki ka wè enfòmasyon sa yo.'}), 403

        now = datetime.utcnow()
        if not room.started_at:
            room.started_at = now
            db.session.commit()
        elapsed_sec = max(0, int((now - room.started_at).total_seconds()))
        elapsed_min = elapsed_sec // 60

        state = active_rooms.get(room_id, {}).get('billing', {}) if room_id in active_rooms else {}

        owner_balance = 0
        try:
            if getattr(current_user, 'whatsapp', None):
                owner_balance = int(GkachService.get_balance(current_user.whatsapp) or 0)
        except Exception:
            owner_balance = 0

        return jsonify({
            'success': True,
            'elapsed_seconds': elapsed_sec,
            'elapsed_minutes': elapsed_min,
            'free_minutes': FREE_MINUTES_DEFAULT,
            'gkach_per_hour': GKACH_PER_HOUR_DEFAULT,
            'reminder_every_min': REMINDER_INTERVAL_MIN,
            'owner_balance': owner_balance,
            'gkach_charged_total': state.get('gkach_charged_total', 0),
            'credit_bought_minutes': state.get('credit_bought_minutes', 0),
            'started_at': room.started_at.isoformat() if room.started_at else None,
        })

    except Exception as e:
        print(f"Error fetching billing: {e}")
        return jsonify({'success': False, 'error': 'Erè nan rekipere fakturasyon an.'}), 500


@konferans_bp.route('/api/charge_hour/<room_id>', methods=['POST'])
@login_required
def charge_gkach_hour(room_id):
    """Charge owner for the next conference hour (250 Gkach/h).

    Called by owner after free 45 minutes to buy 60 additional minutes.
    Atomic: deduct Gkach + update billing state in active_rooms.
    """
    try:
        room = KonferansRoom.query.filter_by(room_id=room_id, is_active=True).first()
        if not room:
            return jsonify({'success': False, 'error': 'Sal sa pa egziste.'}), 404

        if not _room_owner(room):
            return jsonify({'success': False, 'error': 'Se sèl pwopriyete sal la ki ka peye pou sal la.'}), 403

        if not getattr(current_user, 'whatsapp', None):
            return jsonify({'success': False, 'error': 'Ou bezwen yon WhatsApp asosye ak kont ou pou peye Gkach.'}), 400

        amount = GKACH_PER_HOUR_DEFAULT  # 250 Gkach per hour
        minutes_bought = 60

        try:
            GkachService.deduct_balance(
                current_user.whatsapp,
                amount,
                f"Konferans sal {room.room_code} ({room.room_name}): 60 minit adisyonèl",
                'konferans_charge'
            )
        except ValidationError as ve:
            return jsonify({
                'success': False,
                'error': str(ve),
                'insufficient_balance': True,
                'required': amount,
            }), 402

        # Update in-memory state + DB persistence
        if room_id not in active_rooms:
            active_rooms[room_id] = {'participants': [], 'is_recording': False, 'recording_started_by': None}
        bill = active_rooms[room_id].setdefault('billing', {
            'gkach_charged_total': 0,
            'last_reminder_minutes': 0,
            'free_minutes': FREE_MINUTES_DEFAULT,
            'gkach_per_hour': GKACH_PER_HOUR_DEFAULT,
            'credit_bought_minutes': 0,
            'last_charge_minute': FREE_MINUTES_DEFAULT,
        })
        bill['gkach_charged_total'] = int(bill.get('gkach_charged_total', 0)) + amount
        bill['credit_bought_minutes'] = int(bill.get('credit_bought_minutes', 0)) + minutes_bought

        # Persist to DB so charges survive server restarts (preserve-first)
        try:
            _db_room = KonferansRoom.query.filter_by(room_id=room_id).first()
            if _db_room:
                _db_room.gkach_charged_total = int(getattr(_db_room, 'gkach_charged_total', 0) or 0) + amount
                _db_room.credit_bought_minutes = int(getattr(_db_room, 'credit_bought_minutes', 0) or 0) + minutes_bought
                if not getattr(_db_room, 'gkach_per_hour', None):
                    _db_room.gkach_per_hour = GKACH_PER_HOUR_DEFAULT
                if not getattr(_db_room, 'free_minutes', None):
                    _db_room.free_minutes = FREE_MINUTES_DEFAULT
                db.session.commit()
        except Exception:
            db.session.rollback()

        new_balance = 0
        try:
            new_balance = int(GkachService.get_balance(current_user.whatsapp) or 0)
        except Exception:
            new_balance = 0

        return jsonify({
            'success': True,
            'message': f'Peman reysi! Ou achte 60 minit pou {amount} Gkach.',
            'amount_charged': amount,
            'minutes_bought': minutes_bought,
            'new_balance': new_balance,
            'total_charged': bill['gkach_charged_total'],
            'credit_bought_minutes': bill['credit_bought_minutes'],
        })

    except Exception as e:
        db.session.rollback()
        print(f"Error charging Gkach: {e}")
        return jsonify({'success': False, 'error': 'Erè nan peman Gkach la.'}), 500


@konferans_bp.route('/api/invite/<room_id>', methods=['GET'])
@login_required
def get_invite(room_id):
    """Generate/retrieve shareable invite link + code for a conference room."""
    try:
        room = KonferansRoom.query.filter_by(room_id=room_id, is_active=True).first()
        if not room:
            return jsonify({'success': False, 'error': 'Sal sa pa egziste.'}), 404

        if not _room_owner(room):
            return jsonify({'success': False, 'error': 'Se sèl pwopriyetè sal la ki ka jenere lyen envitasyon.'}), 403

        base_url = request.host_url.rstrip('/')
        join_link = f"{base_url}/konferans/room/{room.room_code}"

        return jsonify({
            'success': True,
            'room_code': room.room_code,
            'room_name': room.room_name,
            'creator_name': room.creator_name,
            'join_link': join_link,
            'invite_code': room.room_code,
            'whatsapp_share': f"https://wa.me/?text={urllib.parse.quote(f'Renwete m nan Konferans Glory2Yah: {room.room_name} | Kòd: {room.room_code} | Lyen: {join_link}')}",
            'sms_share': f"sms:?body={urllib.parse.quote(f'Konferans Glory2Yah - {room.room_name} | Kòd: {room.room_code} | {join_link}')}",
            'has_password': bool(room.password),
        })

    except Exception as e:
        print(f"Error fetching invite: {e}")
        return jsonify({'success': False, 'error': 'Erè nan jenere lyen envitasyon an.'}), 500

@konferans_bp.route('/api/stream/start/<room_id>', methods=['POST'])
@login_required
def start_stream_session(room_id):
    """Owner/admin starts a live-stream session to a social platform.

    Body (JSON): {platform, ingest_url, stream_key, title}
    The raw stream key is never persisted — only a masked version.
    Broadcasts 'streaming_started' to the whole room.
    """
    try:
        room = KonferansRoom.query.filter_by(room_id=room_id, is_active=True).first()
        if not room:
            return jsonify({'success': False, 'error': 'Sal sa pa egziste.'}), 404

        is_admin = bool(getattr(current_user, 'is_admin', False))
        if not _room_owner(room) and not is_admin:
            return jsonify({'success': False, 'error': 'Se sèl pwopriyetè sal la ki ka kòmanse yon difizyon Live.'}), 403

        data = request.get_json(silent=True) or {}
        platform = (data.get('platform') or '').strip().lower()
        ingest_url = (data.get('ingest_url') or '').strip()
        stream_key = (data.get('stream_key') or '').strip()
        title = (data.get('title') or '').strip()[:255]

        if platform not in _STREAM_PLATFORMS:
            return jsonify({'success': False, 'error': 'Platfòm pa valid.'}), 400

        # WhatsApp target = local conference save (no RTMP ingest needed here)
        if platform != 'whatsapp':
            if not ingest_url:
                return jsonify({'success': False, 'error': 'Server URL (ingest) obligatwa pou difizyon RTMP.'}), 400
            if not (ingest_url.startswith('rtmp://') or ingest_url.startswith('rtmps://')):
                return jsonify({'success': False, 'error': 'Server URL dwe kòmanse ak rtmp:// oubyen rtmps://.'}), 400
            if len(stream_key) < 4:
                return jsonify({'success': False, 'error': 'Stream Key a obligatwa (minimum 4 karaktè).'}), 400

        if room_stream_sessions.get(room_id):
            return jsonify({
                'success': False,
                'error': 'Yon difizyon Live deja an kous pou sal sa a.',
                'session': _stream_session_payload(room_id),
            }), 409

        now = datetime.utcnow()
        masked = _mask_stream_key(stream_key)
        started_by = (getattr(current_user, 'name', None) or getattr(current_user, 'pseudo', None) or 'Owner')

        # Persist (masked key only)
        session_row = KonferansStreamSession(
            room_id=room_id,
            platform=platform,
            title=title or None,
            ingest_url=ingest_url or None,
            stream_key_masked=masked,
            status='live',
            started_at=now,
            started_by=started_by,
        )
        db.session.add(session_row)
        db.session.commit()

        room_stream_sessions[room_id] = {
            'platform': platform,
            'title': title or None,
            'ingest_url': ingest_url or None,
            'stream_key_masked': masked,
            'started_at': now,
            'session_db_id': session_row.id,
        }

        payload = _stream_session_payload(room_id) or {}
        _so_emit_stream('streaming_started', payload, room_id)

        plat = _STREAM_PLATFORMS[platform]
        return jsonify({
            'success': True,
            'message': f"Difizyon Live '{plat['label']}' kòmanse!",
            'session': payload,
            'dashboard': plat.get('dashboard'),
            'help': plat.get('help'),
            'ingest_hint': plat.get('ingest_hint'),
        })

    except Exception as e:
        db.session.rollback()
        print(f"Error starting stream: {e}")
        return jsonify({'success': False, 'error': 'Erè nan kòmansman difizyon an.'}), 500


@konferans_bp.route('/api/stream/stop/<room_id>', methods=['POST'])
@login_required
def stop_stream_session(room_id):
    """Owner/admin stops the active live-stream session for a room."""
    try:
        room = KonferansRoom.query.filter_by(room_id=room_id, is_active=True).first()
        if not room:
            return jsonify({'success': False, 'error': 'Sal sa pa egziste.'}), 404

        is_admin = bool(getattr(current_user, 'is_admin', False))
        if not _room_owner(room) and not is_admin:
            return jsonify({'success': False, 'error': 'Se sèl pwopriyetè sal la ki ka sispann difizyon an.'}), 403

        payload = _stop_stream_session(room_id, 'manual')
        if not payload:
            return jsonify({'success': False, 'error': 'Pa gen difizyon Live an kous.'}), 404

        return jsonify({
            'success': True,
            'message': 'Difizyon Live sispann.',
            'duration_seconds': payload.get('duration_seconds'),
        })

    except Exception as e:
        db.session.rollback()
        print(f"Error stopping stream: {e}")
        return jsonify({'success': False, 'error': 'Erè nan sispann difizyon an.'}), 500


@konferans_bp.route('/api/stream/status/<room_id>', methods=['GET'])
def stream_status(room_id):
    """Current live-stream state of a room (public — all participants see the banner)."""
    try:
        room = KonferansRoom.query.filter_by(room_id=room_id, is_active=True).first()
        if not room:
            return jsonify({'success': False, 'error': 'Sal sa pa egziste.'}), 404

        return jsonify({
            'success': True,
            'streaming': bool(room_stream_sessions.get(room_id)),
            'session': _stream_session_payload(room_id),
        })

    except Exception as e:
        print(f"Error fetching stream status: {e}")
        return jsonify({'success': False, 'error': 'Erè nan chajman estati difizyon an.'}), 500


@konferans_bp.route('/api/stream/platforms', methods=['GET'])
def stream_platforms():
    """Expose platform presets (labels, ingest hints, dashboard links)."""
    return jsonify({'success': True, 'platforms': _STREAM_PLATFORMS})


@konferans_bp.route('/upload_recording/<room_id>', methods=['POST'])
@login_required
def upload_recording(room_id):
    """Upload recording file — P2 FIX: login_required + owner/admin + ext/size limits."""
    try:
        if 'recording' not in request.files:
            return jsonify({'success': False, 'message': 'Pa gen dosye anrejistreman.'}), 400

        file = request.files['recording']
        if not file or file.filename == '':
            return jsonify({'success': False, 'message': 'Non dosye vid.'}), 400

        room = KonferansRoom.query.filter_by(room_id=room_id, is_active=True).first()
        if not room:
            return jsonify({'success': False, 'message': 'Sal sa pa egziste.'}), 404

        is_admin = False
        try:
            is_admin = bool(current_user.is_authenticated and getattr(current_user, 'is_admin', False))
        except Exception:
            is_admin = False

        is_owner = False
        try:
            if room.user_id and current_user.is_authenticated and room.user_id == current_user.id:
                is_owner = True
        except Exception:
            is_owner = False
        is_owner = _room_owner(room)
        if not is_owner and not is_admin:
            return jsonify({'success': False, 'message': 'Se sèl pwopriyetè oubyen admin ki ka anrejistre.'}), 403

        safe_fn = secure_filename(str(file.filename))
        _, ext = os.path.splitext(safe_fn.lower())
        if ext not in _ALLOWED_RECORDING_EXTS:
            return jsonify({
                'success': False,
                'message': f'Extansyon {ext or "enkoni"} pa otorize. Sèlman: {", ".join(sorted(_ALLOWED_RECORDING_EXTS))}.'
            }), 400

        max_bytes = _MAX_RECORDING_MB * 1024 * 1024
        cl = request.content_length
        if cl is not None and cl > max_bytes:
            return jsonify({
                'success': False,
                'message': f'Dosye a twò gwo. Maksimòm: {_MAX_RECORDING_MB} MB.'
            }), 413

        recordings_dir = os.path.join('static', 'recordings')
        os.makedirs(recordings_dir, exist_ok=True)

        filename = f"recording_{room_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext or '.webm'}"
        file_path = os.path.join(recordings_dir, filename)
        file.save(file_path)

        try:
            actual_size = os.path.getsize(file_path)
        except OSError:
            actual_size = 0
        if actual_size > max_bytes:
            try:
                os.remove(file_path)
            except OSError:
                pass
            return jsonify({
                'success': False,
                'message': f'Dosye a depase {_MAX_RECORDING_MB} MB apre ekri. Li siprime.'
            }), 413

        recording = KonferansRecording(
            room_id=room_id,
            filename=filename,
            file_path=file_path,
            file_size=actual_size or None,
            expires_at=datetime.utcnow() + timedelta(days=7),
        )
        # Optional human title (WhatsApp audio-save / title-frame features).
        # getattr-guarded: old DBs without the column simply skip it.
        rec_title = (request.form.get('title') or '').strip()[:255]
        if rec_title:
            try:
                recording.title = rec_title
            except Exception:
                pass

        db.session.add(recording)
        db.session.commit()

        download_url = url_for('konferans.download_recording', filename=filename)
        absolute_download = f"{request.host_url.rstrip('/')}{download_url}"
        wa_text = f"Anrejistreman Konferans Glory2Yah: {rec_title or room.room_name} — Telechaje isit la: {absolute_download}"
        return jsonify({
            'success': True,
            'message': 'Anrejistreman telechaje avèk siksè!',
            'filename': filename,
            'title': rec_title or None,
            'file_size': actual_size or None,
            'expires_at': recording.expires_at.isoformat(),
            'download_url': download_url,
            'absolute_download_url': absolute_download,
            'whatsapp_share_url': f"https://wa.me/?text={urllib.parse.quote(wa_text)}",
        })

    except Exception as e:
        db.session.rollback()
        print(f"Error uploading recording: {e}")
        return jsonify({'success': False, 'message': 'Erè nan telechajman anrejistreman an.'}), 500

@konferans_bp.route('/update_room_name', methods=['POST'])
def update_room_name():
    """Update room name — P2 FIX: owner check + broadcast + proper status codes."""
    try:
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form

        room_id = data.get('room_id')
        room_name = (data.get('room_name') or '').strip()

        if not room_id or not room_name:
            return jsonify({'success': False, 'message': 'ID sal la ak non sal la obligatwa.'}), 400

        if len(room_name) > 100:
            return jsonify({'success': False, 'message': 'Non sal la twò long.'}), 400

        room = KonferansRoom.query.filter_by(room_id=room_id).first()
        if not room:
            return jsonify({'success': False, 'message': 'Sal sa pa egziste.'}), 404

        is_owner = _room_owner(room)
        try:
            if current_user.is_authenticated and getattr(current_user, 'is_admin', False):
                is_owner = True
        except Exception:
            pass
        if not is_owner:
            return jsonify({'success': False, 'message': 'Se sèl pwopriyetè oubyen admin ki ka chanje non sal la.'}), 403

        room.room_name = room_name
        db.session.commit()

        try:
            _so_emit_stream('room_name_changed', {
                'room_id': room_id,
                'room_name': room_name
            }, room_id)
        except Exception:
            pass

        return jsonify({
            'success': True,
            'message': f'Non sal la chanje an {room_name}!',
            'room_name': room_name
        })

    except Exception as e:
        db.session.rollback()
        print(f"Error updating room name: {e}")
        return jsonify({'success': False, 'message': 'Erè nan modifye non sal la.'}), 500

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
            is_owner = _room_owner(room)
            if not is_owner:
                return "Ou pa gen dwa telechaje dosye sa a.", 403
        return send_from_directory(recordings_dir, safe, as_attachment=True)

    except Exception as e:
        print(f"Error downloading recording: {e}")
        return "Erè nan telechajman dosye a.", 500


_ALLOWED_MEDIA_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp', '.ico',
                        '.mp4', '.webm', '.mov', '.m4v', '.avi', '.mkv',
                        '.mp3', '.wav', '.ogg', '.m4a', '.flac', '.aac',
                        '.pdf', '.doc', '.docx', '.txt'}
_MAX_MEDIA_MB = 50


@konferans_bp.route('/upload_media', methods=['POST'])
@login_required
def upload_media():
    """Upload media file (image, video, audio, document) — room owner only"""
    try:
        room_id = request.form.get('room_id', '').strip()
        if not room_id:
            return jsonify({'success': False, 'message': 'Room ID obligatwa.'}), 400

        # Verify room exists and is currently active
        room = KonferansRoom.query.filter_by(room_id=room_id, is_active=True).first()
        if not room:
            return jsonify({'success': False, 'message': 'Sal sa pa egziste oubyen li pa aktif.'}), 404

        is_owner = _room_owner(room)
        try:
            if current_user.is_authenticated and getattr(current_user, 'is_admin', False):
                is_owner = True
        except Exception:
            pass
        if not is_owner:
            current_name = (getattr(current_user, 'name', None) or getattr(current_user, 'pseudo', None) or '').strip()
            active_names = {
                str(name).strip().casefold()
                for name in active_rooms.get(room_id, {}).get('participants', [])
                if name
            }
            if not current_user.is_authenticated or not current_name or current_name.casefold() not in active_names:
                return jsonify({'success': False, 'message': 'Se patisipan ki nan sesyon an sèlman ki ka pataje medya.'}), 403

        # Check file present
        if 'media' not in request.files:
            return jsonify({'success': False, 'message': 'Pa gen dosye chwazi.'}), 400
        file = request.files['media']
        if not file or not file.filename:
            return jsonify({'success': False, 'message': 'Dosye vid.'}), 400

        # Validate extension
        fname = secure_filename(file.filename)
        ext = os.path.splitext(fname)[1].lower()
        if ext not in _ALLOWED_MEDIA_EXTS:
            return jsonify({'success': False, 'message': 'Tip dosye pa pèmèt.'}), 400

        # Pre-check content_length (fast-fail before disk I/O)
        max_bytes = _MAX_MEDIA_MB * 1024 * 1024
        cl = request.content_length
        if cl is not None and cl > max_bytes:
            return jsonify({
                'success': False,
                'message': f'Dosye a twò gwo. Maksimòm: {_MAX_MEDIA_MB} MB.'
            }), 413

        # Save file
        media_dir = os.path.abspath(os.path.join(os.getcwd(), 'static', 'uploads', 'konferans'))
        os.makedirs(media_dir, exist_ok=True)
        unique_name = f"{room_id}_{uuid.uuid4().hex[:12]}{ext}"
        file_path = os.path.join(media_dir, unique_name)
        file.save(file_path)

        # Check file size (post-write guard)
        file_size = os.path.getsize(file_path)
        if file_size > max_bytes:
            try:
                os.remove(file_path)
            except OSError:
                pass
            return jsonify({
                'success': False,
                'message': f'Dosye a depase {_MAX_MEDIA_MB} MB apre ekri. Li siprime.'
            }), 413

        # Build URL
        file_url = url_for('static', filename=f'uploads/konferans/{unique_name}')

        # Determine media type
        if ext in {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp', '.ico'}:
            media_type = 'image'
        elif ext in {'.mp4', '.webm', '.mov', '.m4v', '.avi', '.mkv'}:
            media_type = 'video'
        elif ext in {'.mp3', '.wav', '.ogg', '.m4a', '.flac', '.aac'}:
            media_type = 'audio'
        else:
            media_type = 'document'

        return jsonify({
            'success': True,
            'url': file_url,
            'filename': unique_name,
            'original_name': file.filename,
            'media_type': media_type,
            'size': file_size
        })

    except Exception as e:
        print(f"Error uploading media: {e}")
        return jsonify({'success': False, 'message': 'Erè pandan telechajman dosye a.'}), 500