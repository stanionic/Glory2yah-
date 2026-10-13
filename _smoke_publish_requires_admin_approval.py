"""Smoke test: EVERY ad (sell OR publish) requires ADMIN approval before online.

Proves the fix in app/routes/main.py create_post():
  1. A brand-new social POST (ad_type='publish') is created as 'under_review'
     (NOT auto-approved) -> must NOT appear in the public feed.
  2. Once an ADMIN approves it (admin_status='approved') -> it DOES appear.

Uses the in-memory TestingConfig (CSRF + rate-limit disabled, simple cache).
No network: the WhatsApp admin alert is monkeypatched to a no-op.

Run:  python _smoke_publish_requires_admin_approval.py
"""
import os
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

os.environ['FLASK_ENV'] = 'testing'
os.environ['RATELIMIT_ENABLED'] = '0'
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db                      # noqa: E402
from app.models.user import User                     # noqa: E402
from app.models.ad import Ad                         # noqa: E402
import app.services.admin_approval_alerts as AAA     # noqa: E402

# Silence the real WhatsApp send (no provider configured -> daemon thread).
AAA.alert_admin = lambda *a, **k: None

app = create_app('testing')

USER_WA = '+50970000001'
UNIQUE_TEXT = 'SMOKE-PUBLISH-NEEDS-APPROVAL-9f3c7a'

results = []


def check(name, ok, extra=''):
    results.append((name, bool(ok)))
    line = ('PASS' if ok else 'FAIL') + ' - ' + name
    if extra:
        line += ' | ' + str(extra)
    print(line.encode('ascii', 'replace').decode('ascii').replace('\n', ' / '))


with app.app_context():
    db.create_all()
    u = User(name='Smoke User', pseudo='smokeuser', whatsapp=USER_WA, is_active=True)
    u.set_password('smoke-pass-1')
    db.session.add(u)
    db.session.commit()

client = app.test_client()
r = client.post('/auth/login', data={'identifier': USER_WA, 'password': 'smoke-pass-1'},
                follow_redirects=True)
check('login as test user', r.status_code in (200, 302), f'status={r.status_code}')

# 1) create a publish-type social post
r = client.post('/api/posts/create', json={'content': UNIQUE_TEXT, 'type': 'text'})
check('POST /api/posts/create accepted', r.status_code == 200, f'status={r.status_code}')

post_ad = None
with app.app_context():
    post_ad = Ad.query.filter_by(ad_type='publish').order_by(Ad.id.desc()).first()
    if post_ad:
        check('new post persisted (ad_type=publish)', post_ad is not None)
        check('new post is under_review (NOT auto-approved)',
              post_ad.admin_status == 'under_review', f'admin_status={post_ad.admin_status}')
        check('new post payment_status is pending',
              post_ad.payment_status == 'pending', f'payment={post_ad.payment_status}')
    else:
        check('new post persisted (ad_type=publish)', False, 'no publish row found')

# 2) must NOT be online in the public feed while under_review
feed = client.get('/').get_data(as_text=True)
check('under_review post is HIDDEN from public feed', UNIQUE_TEXT not in feed)

# 3) ADMIN approves it -> it goes online
ad_id = post_ad.ad_id if post_ad else None
with app.app_context():
    ad = Ad.query.filter_by(ad_id=ad_id).first()
    ad.admin_status = 'approved'
    db.session.commit()
    from app.services.redis_service import RedisService
    from app import redis_client
    try:
        RedisService(redis_client).invalidate_approved_ads()
    except Exception:
        pass

feed2 = client.get('/').get_data(as_text=True)
check('approved post is now ONLINE in public feed', UNIQUE_TEXT in feed2)

print()
passed = sum(1 for _, ok in results if ok)
failed = [n for n, ok in results if not ok]
print(f'RESULT: {passed}/{len(results)} checks passed')
for n in failed:
    print('  -', n)
sys.exit(1 if failed else 0)
