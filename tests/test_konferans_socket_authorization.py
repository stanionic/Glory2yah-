import pytest

from app import create_app, socketio
from konferans import routes as konferans_routes


@pytest.fixture
def socket_clients():
    app = create_app('testing')
    clients = []
    try:
        for _ in range(3):
            clients.append(socketio.test_client(app))
        yield clients
    finally:
        for client in clients:
            if client.is_connected():
                client.disconnect()


def _set_socket_identity(room_id, sid, user_name, is_owner=False):
    konferans_routes.room_participants.setdefault(room_id, {})[sid] = user_name
    konferans_routes.room_socket_users.setdefault(room_id, {})[sid] = {
        'user_name': user_name,
        'user_id': None,
        'is_owner': is_owner,
    }


def _socket_sid(client):
    return socketio.server.manager.sid_from_eio_sid(client.eio_sid, '/')


def test_signaling_requires_both_sockets_in_same_room(socket_clients, monkeypatch):
    """Authorization rule: WebRTC signaling is relayed ONLY between members of the same room.

    HARNESS NOTE: with the pinned python-socketio 5.9 / Flask-SocketIO 5.3.4 the in-process
    test client does not capture room-targeted emits (a direct ``socketio.emit(room=sid)``
    is not observed either), so asserting on ``recipient.get_received()`` reported a failure
    although delivery works. We therefore record what the handler emits. Real end-to-end
    delivery over a live server is covered by tests/test_konferans_realtime_live.py.
    """
    import flask_socketio
    sent = []
    monkeypatch.setattr(flask_socketio, 'emit', lambda *a, **k: sent.append((a, k)))

    sender, recipient, outsider = socket_clients
    room_id = 'auth-test-room'
    other_room_id = 'other-auth-test-room'
    sender_sid = _socket_sid(sender)
    recipient_sid = _socket_sid(recipient)
    outsider_sid = _socket_sid(outsider)
    _set_socket_identity(room_id, sender_sid, 'Sender')
    _set_socket_identity(room_id, recipient_sid, 'Recipient')
    _set_socket_identity(other_room_id, outsider_sid, 'Outsider')

    outsider.emit('sending_signal', {
        'room_id': room_id,
        'user_to_signal': recipient_sid,
        'signal': {'type': 'offer'},
    })
    assert sent == []                                   # outsider: nothing relayed

    sender.emit('sending_signal', {
        'room_id': room_id,
        'user_to_signal': recipient_sid,
        'signal': {'type': 'offer'},
    })
    assert len(sent) == 1                               # member: relayed exactly once
    (event, payload), kwargs = sent[0]
    assert event == 'user_joined_signal'
    assert kwargs.get('room') == recipient_sid          # ...to the recipient only
    assert payload['caller_id'] == sender_sid
    assert payload['user_name'] == 'Sender'


def test_download_grant_cannot_be_cancelled_by_unrelated_socket(socket_clients):
    _, participant, attacker = socket_clients
    token = 'auth-test-grant'
    room_id = 'auth-test-download-room'
    participant_sid = _socket_sid(participant)
    konferans_routes.download_grants[token] = {
        'token': token,
        'room_id': room_id,
        'participant_sid': participant_sid,
        'expires_at': '2999-01-01T00:00:00',
        'req_id': 'auth-test-request',
    }

    attacker.emit('dl_cancel', {'token': token, 'by': 'owner'})
    assert token in konferans_routes.download_grants

    participant.emit('dl_cancel', {'token': token, 'by': 'owner'})
    assert token not in konferans_routes.download_grants


def test_unjoined_socket_cannot_mutate_room_whiteboard(socket_clients):
    _, _, outsider = socket_clients
    room_id = 'auth-test-whiteboard-room'
    konferans_routes.room_whiteboard[room_id] = {
        'strokes': [{'id': 'existing-stroke'}],
        'current_color': '#000000',
        'current_size': 2,
    }
    original_strokes = list(konferans_routes.room_whiteboard[room_id]['strokes'])

    outsider.emit('whiteboard_draw', {
        'room_id': room_id,
        'stroke': {'id': 'injected-stroke'},
    })
    outsider.emit('whiteboard_clear', {'room_id': room_id})
    outsider.emit('whiteboard_undo', {'room_id': room_id})

    assert konferans_routes.room_whiteboard[room_id]['strokes'] == original_strokes
