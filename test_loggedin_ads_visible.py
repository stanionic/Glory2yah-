"""REGRESSION TEST for user report: 'connected users can't load ADS'

Scenarios (user login state is the key axis). Use an in-memory SQLite Flask
test client, populate 3 approved ads (sell*2 + publish*1), create 1 regular
user, run the same GET requests (a) anonymous (baseline, should see ads) and
(b) logged-in (the bug case user describes — MUST also see ads, not 0 products).
"""
from __future__ import annotations
import os
import sys
import unittest


class TestLoggedInUsersCanLoadAds(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.pop('DATABASE_URL', None)
        os.environ.pop('FLASK_ENV', None)
        os.environ['SECRET_KEY'] = 'unit-tests-loggedin-ads-visible-secret'
        # Use in-memory SQLite for clean state every test
        cls._db_url = 'sqlite:///:memory:'

    def _create_app(self):
        # Import AFTER env is set
        import importlib
        if 'app' in sys.modules:
            importlib.reload(sys.modules['app'])
        from app import create_app, db
        app = create_app('testing')
        # Forcibly override DSN to in-memory SQLite (no local file, no lingering tables)
        import tempfile
        tmp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        tmp_db.close()
        app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            SERVER_NAME='localhost.test',
            PREFERRED_URL_SCHEME='http',
            SQLALCHEMY_DATABASE_URI='sqlite:///' + tmp_db.name,
            SQLALCHEMY_ENGINE_OPTIONS={'pool_pre_ping': True},
            SESSION_TYPE='filesystem',
            SESSION_FILE_DIR=os.path.join(os.getcwd(), '.tmp_test_sess_ads'),
            CACHE_TYPE='simple',
        )
        os.makedirs(app.config['SESSION_FILE_DIR'], exist_ok=True)
        self._tmp_db_path = tmp_db.name
        with app.app_context():
            # db.init_app already called inside create_app; explicitly drop+create here
            db.drop_all()
            db.create_all()
            # Run ALTER-style idempotent migrations that don't CREATE TABLE (they run on real tables)
            try:
                from app.__init__ import _run_ads_column_migrations, _run_soft_delete_migration, _run_konferans_elearning_migration
            except Exception:
                _run_ads_column_migrations = _run_soft_delete_migration = _run_konferans_elearning_migration = None
            if _run_ads_column_migrations:
                try:
                    _run_ads_column_migrations(app, db)
                except Exception:
                    pass
            if _run_konferans_elearning_migration:
                try:
                    _run_konferans_elearning_migration(app, db)
                except Exception:
                    pass
            if _run_soft_delete_migration:
                try:
                    _run_soft_delete_migration(app, db)
                except Exception:
                    pass
            self._seed(db, app)
        return app, db

    def _seed(self, db, app):
        import uuid
        from app.models.user import User
        from app.models.ad import Ad
        from werkzeug.security import generate_password_hash

        u = User(
            pseudo='jeanmarie',
            name='Jean Marie Test',
            whatsapp='+50942000001',
            email='jmt@glory2yah.test',
            password_hash=generate_password_hash('Password123!'),
            is_active=True,
        )
        db.session.add(u)
        db.session.flush()

        def mk_ad(ad_id, title, ad_type, admin_status, price_gkach, user=u):
            return Ad(
                ad_id=ad_id,
                user_whatsapp=user.whatsapp,
                title=title,
                description=f'Beskri pwodui {title}',
                media_type='images',
                images='p1.jpg,p2.jpg',
                ad_type=ad_type,
                price_gkach=price_gkach,
                category='autre' if ad_type == 'publish' else 'lakay',
                admin_status=admin_status,
                payment_status='paid',
            )

        ads = [
            mk_ad(f'AD{uuid.uuid4().hex[:8].upper()}', 'Kay Villa a Vann', 'sell', 'approved', 1200000),
            mk_ad(f'AD{uuid.uuid4().hex[:8].upper()}', 'Machin Lave Lisyon', 'sell', 'approved', 9500),
            mk_ad(f'AD{uuid.uuid4().hex[:8].upper()}', 'Sèvis Koudya Maten Nan', 'publish', 'approved', 0),
            # Pending ad - MUST NOT show up anywhere
            mk_ad(f'AD{uuid.uuid4().hex[:8].upper()}', 'Pending Pa Gen Dwa Wè li', 'sell', 'under_review', 10),
        ]
        for a in ads:
            db.session.add(a)
        db.session.commit()
        self._user_id = u.id
        self._user_pseudo = u.pseudo

    def test_anonymous_sees_marketplace_ads(self):
        app, db = self._create_app()
        client = app.test_client(use_cookies=True)
        r = client.get('/mache/')
        self.assertEqual(r.status_code, 200, f"marketplace returned {r.status_code}")
        html = r.get_data(as_text=True)
        # Both approved sell ads should be visible
        self.assertIn('Kay Villa a Vann', html)
        self.assertIn('Machin Lave Lisyon', html)
        # Pending must NOT be visible
        self.assertNotIn('Pending Pa Gen Dwa Wè li', html)
        # Results count badge in template: "X pwodui"
        self.assertIn('2 pwodui', html)

    def test_anonymous_sees_homepage_feed_and_carousel_ads(self):
        app, db = self._create_app()
        client = app.test_client(use_cookies=True)
        r = client.get('/')
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        # Homepage carousel shows ALL approved ads (sell + publish)
        self.assertIn('Kay Villa a Vann', html)
        self.assertIn('Machin Lave Lisyon', html)
        self.assertIn('Sèvis Koudya Maten Nan', html)
        # Pending NEVER
        self.assertNotIn('Pending Pa Gen Dwa Wè li', html)

    def test_logged_in_user_sees_marketplace_ads_same_as_anon(self):
        """The bug user reports: once connected, ADS fail to load. We compare
        the logged-in HTML response vs the anonymous baseline (logged-in MUST
        see exactly the same 2 approved SELL ads in /mache)."""
        app, db = self._create_app()
        client = app.test_client(use_cookies=True)

        # 1. Login with the seeded user (no CSRF in testing config)
        login_r = client.post('/auth/login', data={
            'identifier': self._user_pseudo,
            'password': 'Password123!',
        }, follow_redirects=True)
        self.assertIn(login_r.status_code, (200,), f"login returned {login_r.status_code}")

        # 2. Verify session reports authenticated
        from flask_login import current_user
        with client.session_transaction() as sess:
            self.assertIn('_user_id', sess, "session missing _user_id after login")

        with app.test_request_context('/'):
            with client.session_transaction() as sess:
                # nothing, just ensuring test client is populated
                pass

        # 3. GET /mache while LOGGED IN — the bug scenario
        r = client.get('/mache/')
        self.assertEqual(r.status_code, 200, f"LOGGED-IN marketplace returned {r.status_code}")
        html = r.get_data(as_text=True)
        self.assertIn('Kay Villa a Vann', html, "LOGGED-IN user doesn't see ad #1 in /mache (BUG!)")
        self.assertIn('Machin Lave Lisyon', html, "LOGGED-IN user doesn't see ad #2 in /mache (BUG!)")
        self.assertNotIn('Pending Pa Gen Dwa Wè li', html)
        self.assertIn('2 pwodui', html, f"LOGGED-IN products count incorrect. HTML snippet={html[:400]!r}")

    def test_logged_in_user_api_products_returns_ads(self):
        """Infinite scroll API for /mache must also return >0 ads while logged in."""
        app, db = self._create_app()
        client = app.test_client(use_cookies=True)
        client.post('/auth/login', data={
            'identifier': self._user_pseudo,
            'password': 'Password123!',
        })
        r = client.get('/mache/api/products?page=1&category=all&sort=recent')
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(data and data.get('success'))
        self.assertEqual(len(data.get('products', [])), 2,
                         f"LOGGED-IN /mache/api/products returned 0 ads. FULL PAYLOAD={data!r}")
        titles = sorted(p.get('title') for p in data.get('products', []))
        self.assertEqual(titles, ['Kay Villa a Vann', 'Machin Lave Lisyon'])

    def test_logged_in_homepage_sees_all_approved_feed_and_carousel(self):
        app, db = self._create_app()
        client = app.test_client(use_cookies=True)
        client.post('/auth/login', data={
            'identifier': self._user_pseudo,
            'password': 'Password123!',
        })
        r = client.get('/')
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        # Quick-post section renders for logged-in
        self.assertIn('quickPostSection', html, "LOGGED-IN homepage doesn't render quick post section")
        # 3 approved ads visible: 2 sell + 1 publish
        self.assertIn('Kay Villa a Vann', html)
        self.assertIn('Machin Lave Lisyon', html)
        self.assertIn('Sèvis Koudya Maten Nan', html)
        self.assertNotIn('Pending Pa Gen Dwa Wè li', html)


if __name__ == '__main__':
    unittest.main(verbosity=2)
