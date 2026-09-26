# -*- coding: utf-8 -*-
"""
Validation E2E de la logique de récompense Gkach (anti-fraud).
Base SQLite FICHIER (persistance réelle entre requêtes, comme en prod).
"""
import os
import tempfile
import unittest
import uuid
from urllib.parse import quote

os.environ['FLASK_ENV'] = 'testing'

from app.config import TestingConfig

_DBFILE = os.path.join(tempfile.gettempdir(), 'g2y_reward_%s.db' % uuid.uuid4().hex)
TestingConfig.SQLALCHEMY_DATABASE_URI = 'sqlite:///' + _DBFILE
TestingConfig.SQLALCHEMY_ENGINE_OPTIONS = {'pool_pre_ping': True}

from app import create_app, db
from app.models.batch import Batch
from app.models.batch_click import BatchClick
from app.models.user import User
from app.models.user_gkach import UserGkach
from app.services.gkach_service import GkachService

REFERRER = '+50942882076'

app = create_app()  # crée + seed tables sur le fichier DB


def _base_url(ip):
    return '/s/b/B1?r=' + quote(REFERRER, safe='')


class RewardE2ETest(unittest.TestCase):

    def setUp(self):
        self.ctx = app.app_context()
        self.ctx.push()
        db.drop_all()
        db.create_all()
        db.session.add(Batch(batch_id='B1', share_count=0, click_rewards=0))
        db.session.add(UserGkach(user_whatsapp=REFERRER, gkach_balance=0))
        for i in range(6):
            u = User(whatsapp='+5095000%04d' % i, pseudo='U%d' % i,
                     is_active=True, email='u%d@x.com' % i)
            u.set_password('p')
            db.session.add(u)
        a = User(whatsapp=REFERRER, pseudo='Admin509', is_admin=True,
                 is_active=True, email='a@x.com')
        a.set_password('ap')
        db.session.add(a)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.engine.dispose()
        self.ctx.pop()

    # ---------------- SERVICE LEVEL ----------------
    def test_service_device_limit(self):
        ok1 = GkachService.track_batch_click('B1', REFERRER,
                                             clicker_whatsapp='+50950000000',
                                             clicker_device='dev-AAA')
        ok2 = GkachService.track_batch_click('B1', REFERRER,
                                             clicker_whatsapp='+50950000001',
                                             clicker_device='dev-AAA')
        self.assertTrue(ok1)
        self.assertFalse(ok2)

    def test_service_ip_limit(self):
        for i in range(3):
            self.assertTrue(GkachService.track_batch_click(
                'B1', REFERRER, clicker_whatsapp='+5095000%04d' % i,
                clicker_ip='1.2.3.4'))
        self.assertFalse(GkachService.track_batch_click(
            'B1', REFERRER, clicker_whatsapp='+5095000033',
            clicker_ip='1.2.3.4'))

    def test_service_blocked_ip(self):
        GkachService.set_blocked_ips(['5.5.5.5'])
        self.assertTrue(GkachService._is_ip_blocked('5.5.5.5'))
        self.assertFalse(GkachService._is_ip_blocked('8.8.8.8'))
        self.assertFalse(GkachService.track_batch_click(
            'B1', REFERRER, clicker_whatsapp='+50950000000',
            clicker_ip='5.5.5.5', clicker_device='dev-X'))
        self.assertTrue(GkachService.track_batch_click(
            'B1', REFERRER, clicker_whatsapp='+50950000000',
            clicker_ip='8.8.8.8', clicker_device='dev-X'))

    def test_service_reward_auto_credit(self):
        for i in range(100):
            GkachService.track_batch_click('B1', REFERRER,
                                           clicker_whatsapp='+5095000%04d' % i,
                                           clicker_ip='10.0.0.%d' % i,
                                           clicker_device='dev-%d' % i)
        bal = UserGkach.query.filter_by(user_whatsapp=REFERRER).first()
        b = Batch.query.filter_by(batch_id='B1').first()
        self.assertEqual(bal.gkach_balance, 10)
        self.assertEqual(b.share_count, 100)

    # ---------------- ROUTE LEVEL (device cookie) ----------------
    def test_route_device_cookie_and_limit(self):
        c = app.test_client()
        with c:
            c.post('/auth/login', data={'identifier': 'U0', 'password': 'p'})
            r = c.get(_base_url('9.9.9.9'), headers={'X-Forwarded-For': '9.9.9.9'})
            self.assertEqual(r.status_code, 302)
            cookie_val = None
            for h in r.headers.getlist('Set-Cookie'):
                if h.startswith('g2y_device='):
                    cookie_val = h.split(';')[0].split('=', 1)[1]
            self.assertTrue(cookie_val and '.' in cookie_val,
                            'cookie doit être signé')
            # même device, autre compte => bloqué
            c.post('/auth/login', data={'identifier': 'U1', 'password': 'p'})
            c.get(_base_url('9.9.9.9'), headers={'X-Forwarded-For': '9.9.9.9'})
            self.assertEqual(BatchClick.query.count(), 1)

    # ---------------- ADMIN (block/unblock IP) ----------------
    def test_admin_block_unblock_http(self):
        ca = app.test_client()
        with ca:
            ca.post('/auth/login', data={'identifier': 'Admin509',
                                         'password': 'ap'})
            self.assertEqual(ca.get('/admin/rewards').status_code, 200)
            ca.post('/admin/rewards/block-ip', data={'ip': '5.5.5.5'})
            self.assertIn('5.5.5.5', GkachService.get_blocked_ips())

            # cliqueur depuis cette IP (device neuf) = ignoré
            c2 = app.test_client()
            with c2:
                c2.post('/auth/login', data={'identifier': 'U2', 'password': 'p'})
                c2.get(_base_url('5.5.5.5'), headers={'X-Forwarded-For': '5.5.5.5'})
            self.assertEqual(BatchClick.query.count(), 0)

            # unblock
            ca.post('/admin/rewards/unblock-ip', data={'ip': '5.5.5.5'})
            self.assertNotIn('5.5.5.5', GkachService.get_blocked_ips())

    def test_admin_rewards_page_renders(self):
        ca = app.test_client()
        with ca:
            ca.post('/auth/login', data={'identifier': 'Admin509',
                                         'password': 'ap'})
            r = ca.get('/admin/rewards')
            self.assertEqual(r.status_code, 200)
            html = r.get_data(as_text=True)
            self.assertIn('Bloke Adrès IP', html)


if __name__ == '__main__':
    unittest.main(verbosity=2)
