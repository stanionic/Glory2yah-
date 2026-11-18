"""KONFERANS stream relay: the ingest URL must be a PUBLIC rtmp(s) host (no SSRF to internal hosts)."""
import os
import socket
import sys
import uuid

import pytest

os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('SECRET_KEY', 'konferans-ingest-secret')
os.environ.setdefault('WTF_CSRF_ENABLED', 'False')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from konferans import stream_relay as sr

PUBLIC_IP = '142.250.74.46'


def fake_dns(table):
    """A resolver that answers from a dict {host: [ips]} and fails (gaierror) otherwise."""
    def resolve(host, port, type=None):
        if host not in table:
            raise socket.gaierror('unknown host')
        return [(socket.AF_INET6 if ':' in ip else socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, port))
                for ip in table[host]]
    return resolve


DNS = fake_dns({
    'live-api-s.facebook.com': [PUBLIC_IP], 'a.rtmp.youtube.com': [PUBLIC_IP, '2a00:1450:4007::5e'],
    'push.tiktokcdn.com': ['23.45.67.89'], 'rtmp.example.org': ['93.184.216.34'],
    'evil.example': ['10.0.0.5'], 'mixed.example': [PUBLIC_IP, '192.168.1.10'],
    'meta.example': ['169.254.169.254'], 'loop.example': ['127.0.0.1'], 'v6loop.example': ['::1'],
    'mapped.example': ['::ffff:127.0.0.1'], 'cgnat.example': ['100.64.0.9'], 'empty.example': [],
    # internal-looking names that a (hostile or misconfigured) DNS answers with a PUBLIC address:
    # they must be refused by NAME, independently of what they resolve to.
    'db.internal': [PUBLIC_IP], 'printer.local': [PUBLIC_IP], 'nas.lan': [PUBLIC_IP],
    'router.home.arpa': [PUBLIC_IP], 'localhost': [PUBLIC_IP], 'host.localdomain': [PUBLIC_IP],
})

GOOD = [
    'rtmps://live-api-s.facebook.com:443/rtmp/',            # Facebook preset
    'rtmp://a.rtmp.youtube.com/live2',                      # YouTube preset
    'rtmp://push.tiktokcdn.com/live',                       # TikTok preset
    'rtmp://rtmp.example.org:1935/app',                     # custom RTMP
    'RTMP://RTMP.EXAMPLE.ORG/app',                          # case-insensitive
    'rtmp://8.8.8.8/live',                                  # public IP literal
    'rtmp://[2606:4700:4700::1111]/live',                   # public IPv6 literal
]


@pytest.mark.parametrize('url', GOOD)
def test_public_rtmp_destinations_are_accepted(url):
    assert sr.validate_ingest_url(url, resolver=DNS) == (True, None)


BAD = [
    # wrong / dangerous schemes
    'http://rtmp.example.org/live', 'https://rtmp.example.org', 'file:///etc/passwd', 'ftp://a.b/c',
    'rtsp://rtmp.example.org/x', 'javascript:alert(1)', '//rtmp.example.org/live', 'rtmp.example.org/live',
    # internal targets
    'rtmp://localhost/live', 'rtmp://LOCALHOST/live', 'rtmp://localhost./live', 'rtmp://127.0.0.1/live',
    'rtmp://127.1.2.3:1935/live', 'rtmp://10.0.0.1/live', 'rtmp://172.16.5.4/live',
    'rtmp://192.168.1.1/live', 'rtmp://169.254.169.254/latest/meta-data', 'rtmp://100.64.0.1/live',
    'rtmp://0.0.0.0/live', 'rtmp://224.0.0.1/live', 'rtmp://[::1]/live', 'rtmp://[fd00::1]/live',
    'rtmp://[fe80::1]/live', 'rtmp://[::ffff:127.0.0.1]/live', 'rtmp://[::ffff:10.0.0.1]/live',
    'rtmp://db.internal/live', 'rtmp://printer.local/live', 'rtmp://nas.lan/live',
    'rtmp://router.home.arpa/live', 'rtmp://host.localdomain/live',
    # names that RESOLVE to internal addresses
    'rtmp://evil.example/live', 'rtmp://mixed.example/live', 'rtmp://meta.example/live',
    'rtmp://loop.example/live', 'rtmp://v6loop.example/live', 'rtmp://mapped.example/live',
    'rtmp://cgnat.example/live', 'rtmp://empty.example/live', 'rtmp://does-not-resolve.example/live',
    # smuggling / malformed
    'rtmp://rtmp.example.org@127.0.0.1/live', 'rtmp://user:pw@rtmp.example.org/live',
    'rtmp://rtmp.example.org:0/live', 'rtmp://rtmp.example.org:70000/live', 'rtmp://rtmp.example.org:abc/live',
    'rtmp://rtmp.example.org/live key', 'rtmp://rtmp.example.org/live\nX', 'rtmp://rtmp.example.org\\@127.0.0.1',
    'rtmp://rtmp.example.org/' + 'a' * 2100, 'rtmp://', 'rtmp:///live', '', '   ', None,
]


@pytest.mark.parametrize('url', BAD)
def test_unsafe_or_malformed_destinations_are_rejected(url):
    ok, err = sr.validate_ingest_url(url, resolver=DNS)
    assert ok is False and isinstance(err, str) and err


def test_error_messages_never_echo_the_url_or_stream_key():
    secret = 'SUPER-SECRET-KEY-123'
    for url in ('rtmp://127.0.0.1/' + secret, 'http://x/' + secret, 'rtmp://evil.example/' + secret):
        ok, err = sr.validate_ingest_url(url, resolver=DNS)
        assert not ok and secret not in err and '127.0.0.1' not in err and 'evil.example' not in err


def test_a_dns_failure_is_a_clean_rejection_not_a_crash():
    def broken(*a, **k):
        raise OSError('network down')
    ok, err = sr.validate_ingest_url('rtmp://rtmp.example.org/live', resolver=broken)
    assert ok is False and 'DNS' in err


# ---------------------------- the relay's choke point -------------------------
@pytest.fixture()
def no_ffmpeg(monkeypatch):
    """Record any attempt to start ffmpeg instead of spawning it."""
    started = []
    monkeypatch.setattr(sr._StreamBroadcaster, 'start', lambda self: (started.append(self.url), (True, None))[1])
    monkeypatch.setattr(sr, '_ffmpeg_binary', lambda: '/usr/bin/true')
    return started


@pytest.mark.parametrize('url', ['rtmp://127.0.0.1/live', 'rtmp://169.254.169.254/x', 'http://rtmp.example.org/x',
                                 'rtmp://evil.example/live', 'file:///etc/passwd'])
def test_start_broadcaster_refuses_unsafe_urls_before_spawning_ffmpeg(monkeypatch, no_ffmpeg, url):
    monkeypatch.setattr(sr.socket, 'getaddrinfo', DNS)
    room = 'ingest-' + uuid.uuid4().hex[:8]
    ok, err, info = sr.start_broadcaster(room, url, 'KEY123')
    assert (ok, info) == (False, None) and err
    assert no_ffmpeg == [] and room not in sr._broadcasters
    assert 'KEY123' not in err


def test_start_broadcaster_still_works_for_legitimate_destinations(monkeypatch, no_ffmpeg):
    monkeypatch.setattr(sr.socket, 'getaddrinfo', DNS)
    room = 'ingest-' + uuid.uuid4().hex[:8]
    try:
        ok, err, info = sr.start_broadcaster(room, 'rtmp://a.rtmp.youtube.com/live2', 'abcd-1234')
        assert ok is True and err is None and info['relay'] is True
        assert no_ffmpeg == ['rtmp://a.rtmp.youtube.com/live2/abcd-1234']      # key appended as before
    finally:
        sr.stop_broadcaster(room)


# ------------------------------ the HTTP route end to end ---------------------
from app import create_app, db
from app.models.konferans import KonferansRoom
from app.models.user import User


@pytest.fixture()
def app():
    a = create_app('testing')
    a.config['WTF_CSRF_ENABLED'] = False
    yield a
    with a.app_context():
        db.session.remove()
        db.drop_all()


def _owner_and_room(app, admin=False):
    with app.app_context():
        wa = '+5094' + str(uuid.uuid4().int)[:7]
        u = User(whatsapp=wa, pseudo='k' + uuid.uuid4().hex[:10], name='Owner', auth_provider='whatsapp',
                 is_active=True, is_admin=admin)
        u.set_password('Str0ng-Passw0rd!')
        db.session.add(u)
        db.session.commit()
        room = KonferansRoom(room_id='room-' + uuid.uuid4().hex[:10], room_code=uuid.uuid4().hex[:8].upper(),
                             room_name='Test room', creator_name='Owner', user_id=u.id, creator_whatsapp=wa,
                             is_active=True)
        db.session.add(room)
        db.session.commit()
        return u.id, room.room_id


def _login(app, uid):
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(uid)
        s['_fresh'] = True
    return c


def _start(app, uid, rid, ingest, platform='youtube'):
    return _login(app, uid).post(f'/konferans/api/stream/start/{rid}', json={
        'platform': platform, 'ingest_url': ingest, 'stream_key': 'KEY-xyz-789', 'title': 'Live'})


@pytest.mark.parametrize('ingest', ['rtmp://127.0.0.1/live', 'rtmp://169.254.169.254/latest', 'rtmp://10.1.2.3/x',
                                    'rtmp://evil.example/live', 'rtmp://localhost/live'])
def test_route_rejects_internal_ingest_hosts_with_a_clear_message(app, monkeypatch, ingest):
    monkeypatch.setattr(sr.socket, 'getaddrinfo', DNS)
    uid, rid = _owner_and_room(app)
    r = _start(app, uid, rid, ingest)
    assert r.status_code == 400 and r.json['success'] is False
    assert 'KEY-xyz-789' not in r.get_data(as_text=True) and ingest not in r.get_data(as_text=True)


def test_route_keeps_accepting_the_real_platform_presets(app, monkeypatch):
    monkeypatch.setattr(sr.socket, 'getaddrinfo', DNS)
    for platform, ingest in (('youtube', 'rtmp://a.rtmp.youtube.com/live2'),
                             ('tiktok', 'rtmp://push.tiktokcdn.com/live'),
                             ('facebook', 'rtmps://live-api-s.facebook.com:443/rtmp/')):
        uid, rid = _owner_and_room(app)
        r = _start(app, uid, rid, ingest, platform)
        assert r.status_code == 200 and r.json['success'] is True, (platform, r.get_json())


def test_route_still_enforces_ownership_and_old_prefix_rule(app, monkeypatch):
    monkeypatch.setattr(sr.socket, 'getaddrinfo', DNS)
    uid, rid = _owner_and_room(app)
    stranger, _ = _owner_and_room(app)
    assert _start(app, stranger, rid, 'rtmp://a.rtmp.youtube.com/live2').status_code == 403
    assert _start(app, uid, rid, 'http://a.rtmp.youtube.com/live2').status_code == 400
    assert _start(app, uid, rid, '').status_code == 400
