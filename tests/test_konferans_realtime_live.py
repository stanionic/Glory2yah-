"""KONFERANS real-time baseline over a LIVE Socket.IO server (real clients, real transport).

Why: the in-process Socket.IO test client cannot observe room-targeted emits with the pinned
library versions, so delivery-level behaviour has to be checked against a running server.
These are the reference tests that Phase 2+ changes must keep green.
"""
import os
import socket
import sys
import threading
import time

import pytest

os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('SECRET_KEY', 'konferans-live-secret')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

sio_client = pytest.importorskip('socketio')
pytest.importorskip('requests')

from app import create_app, socketio
from konferans import routes as kr


def _free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


@pytest.fixture(scope='module')
def server():
    app = create_app('testing')
    port = _free_port()
    threading.Thread(target=lambda: socketio.run(
        app, host='127.0.0.1', port=port, allow_unsafe_werkzeug=True, use_reloader=False,
        log_output=False), daemon=True).start()
    for _ in range(50):                                   # wait until it accepts connections
        try:
            socket.create_connection(('127.0.0.1', port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    yield f'http://127.0.0.1:{port}'


def _client(url, inbox, event='user_joined_signal'):
    c = sio_client.Client(reconnection=False)
    c.on(event, lambda data: inbox.append(data))
    c.connect(url, transports=['polling'], wait_timeout=8)
    return c


def _seed(room, sid, name, is_owner=False):
    kr.room_participants.setdefault(room, {})[sid] = name
    kr.room_socket_users.setdefault(room, {})[sid] = {
        'user_name': name, 'user_id': None, 'is_owner': is_owner}


def _wait(cond, timeout=4.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_clients_can_connect_and_get_distinct_sessions(server):
    boxes, clients = [[], [], []], []
    try:
        clients = [_client(server, b) for b in boxes]
        sids = [c.get_sid() for c in clients]
        assert all(sids) and len(set(sids)) == 3
    finally:
        for c in clients:
            c.disconnect()


def test_signaling_is_delivered_to_room_members_and_never_to_outsiders(server):
    got_b, got_c, got_a = [], [], []
    a, b, c = _client(server, got_a), _client(server, got_b), _client(server, got_c)
    try:
        sa, sb, sc = a.get_sid(), b.get_sid(), c.get_sid()
        room, other = f'live-room-{sa[:6]}', f'live-other-{sa[:6]}'
        _seed(room, sa, 'Sender')
        _seed(room, sb, 'Recipient')
        _seed(other, sc, 'Outsider')

        c.emit('sending_signal', {'room_id': room, 'user_to_signal': sb, 'signal': {'type': 'offer'}})
        time.sleep(1.0)
        assert got_b == []                                       # outsider cannot reach the recipient

        a.emit('sending_signal', {'room_id': room, 'user_to_signal': sb, 'signal': {'type': 'offer'}})
        assert _wait(lambda: len(got_b) == 1)                    # member can
        assert got_b[0]['caller_id'] == sa and got_b[0]['user_name'] == 'Sender'
        assert got_b[0]['signal'] == {'type': 'offer'}
        time.sleep(0.5)
        assert got_c == [] and got_a == []                       # nobody else hears it
    finally:
        for cl in (a, b, c):
            cl.disconnect()
        for r in list(kr.room_participants):
            if r.startswith('live-'):
                kr.room_participants.pop(r, None)
                kr.room_socket_users.pop(r, None)


def test_signaling_to_oneself_or_to_unknown_peers_is_dropped(server):
    got_a, got_b = [], []
    a, b = _client(server, got_a), _client(server, got_b)
    try:
        sa, sb = a.get_sid(), b.get_sid()
        room = f'live-room2-{sa[:6]}'
        _seed(room, sa, 'Sender')
        _seed(room, sb, 'Recipient')
        a.emit('sending_signal', {'room_id': room, 'user_to_signal': sa, 'signal': {'t': 1}})   # self
        a.emit('sending_signal', {'room_id': room, 'user_to_signal': 'nope', 'signal': {'t': 1}})
        a.emit('sending_signal', {'room_id': room, 'user_to_signal': sb})                        # no signal
        a.emit('sending_signal', None)
        time.sleep(1.0)
        assert got_a == [] and got_b == []
    finally:
        a.disconnect()
        b.disconnect()
