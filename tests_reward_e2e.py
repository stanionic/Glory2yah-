# -*- coding: utf-8 -*-
"""
Validation E2E de la logique de récompense Gkach (anti-fraud).
Base SQLite FICHIER (persistance réelle entre requêtes, comme en prod).
"""
import os
import tempfile
import unittest
import uuid
from unittest.mock import patch
from urllib.parse import quote

os.environ['FLASK_ENV'] = 'testing'

from app.config import TestingConfig

_DBFILE = os.path.join(tempfile.gettempdir(), 'g2y_reward_%s.db' % uuid.uuid4().hex)
TestingConfig.SQLALCHEMY_DATABASE_URI = 'sqlite:///' + _DBFILE
TestingConfig.SQLALCHEMY_ENGINE_OPTIONS = {'pool_pre_ping': True}

from app import create_app, db
from app.models.batch import Batch
from app.models.batch_ad import BatchAd
from app.models.batch_click import BatchClick
from app.models.ad import Ad
from app.models.user import User
from app.models.user_gkach import UserGkach
from app.models.gkach_transaction import GkachTransaction
from app.routes.share import _get_client_ip, create_batch_referral_token
from app.services.gkach_service import GkachService

REFERRER = '+50942882076'

app = create_app()  # crée + seed tables sur le fichier DB


def _base_url(user_id=None):
    if user_id is None:
        user_id = User.query.filter_by(whatsapp=REFERRER).first().id
    token = create_batch_referral_token('B1', user_id)
    return '/s/b/B1?ref=' + quote(token, safe='')


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
        db.session.flush()
        ad = Ad(
            ad_id='A1',
            user_whatsapp=REFERRER,
            title='Approved test ad',
            description='Shareable ad',
            admin_status='approved',
            payment_status='paid',
        )
        db.session.add(ad)
        db.session.flush()
        db.session.add(BatchAd(batch_id='B1', ad_id='A1', position=0))
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
        self.assertEqual(b.click_rewards, 10)
        self.assertEqual(
            GkachTransaction.query.filter_by(
                user_whatsapp=REFERRER, transaction_type='reward',
            ).count(),
            1,
        )
        self.assertFalse(GkachService.track_batch_click(
            'B1', REFERRER, clicker_whatsapp='+50950000099',
            clicker_ip='10.0.0.99', clicker_device='dev-99',
        ))
        self.assertEqual(bal.gkach_balance, 10)

    def test_rewards_are_paid_once_per_milestone(self):
        for i in range(200):
            self.assertTrue(GkachService.track_batch_click(
                'B1', REFERRER,
                clicker_whatsapp='+5096%07d' % i,
                clicker_ip='10.1.%d.%d' % (i // 250, i % 250),
                clicker_device='milestone-device-%d' % i,
            ))
        account = UserGkach.query.filter_by(user_whatsapp=REFERRER).first()
        batch = Batch.query.filter_by(batch_id='B1').first()
        rewards = GkachTransaction.query.filter_by(
            user_whatsapp=REFERRER, transaction_type='reward',
        ).count()
        self.assertEqual(account.gkach_balance, 20)
        self.assertEqual(batch.click_rewards, 20)
        self.assertEqual(batch.share_count, 200)
        self.assertEqual(rewards, 2)

    # ---------------- ROUTE LEVEL (device cookie) ----------------
    def test_route_ignores_client_supplied_referrer(self):
        c = app.test_client()
        with c:
            c.post('/auth/login', data={'identifier': 'U0', 'password': 'p'})
            malicious_url = _base_url() + '&r=' + quote('+50950000000', safe='')
            r = c.get(malicious_url, environ_base={'REMOTE_ADDR': '9.9.9.9'})
            self.assertEqual(r.status_code, 200)
            self.assertIn(b'Approved test ad', r.data)
            self.assertEqual(BatchClick.query.filter_by(referrer_whatsapp=REFERRER).count(), 1)
            self.assertEqual(BatchClick.query.filter_by(referrer_whatsapp='+50950000000').count(), 0)
            self.assertIsNone(UserGkach.query.filter_by(user_whatsapp='+50950000000').first())

    def test_route_device_cookie_and_limit(self):
        c = app.test_client()
        with c:
            c.post('/auth/login', data={'identifier': 'U0', 'password': 'p'})
            r = c.get(_base_url(), environ_base={'REMOTE_ADDR': '9.9.9.9'})
            self.assertEqual(r.status_code, 200)
            cookie_val = None
            for h in r.headers.getlist('Set-Cookie'):
                if h.startswith('g2y_device='):
                    cookie_val = h.split(';')[0].split('=', 1)[1]
            self.assertTrue(cookie_val and '.' in cookie_val,
                            'cookie doit être signé')
            # même device, autre compte => bloqué
            c.post('/auth/login', data={'identifier': 'U1', 'password': 'p'})
            c.get(_base_url(), environ_base={'REMOTE_ADDR': '9.9.9.9'})
            self.assertEqual(BatchClick.query.count(), 1)

    def test_invalid_referral_token_is_not_counted(self):
        c = app.test_client()
        with c:
            c.post('/auth/login', data={'identifier': 'U0', 'password': 'p'})
            response = c.get('/s/b/B1?ref=forged-token')
            self.assertEqual(response.status_code, 302)
            self.assertEqual(BatchClick.query.count(), 0)

    def test_anonymous_click_resumes_after_login(self):
        c = app.test_client()
        share_url = _base_url()
        response = c.get(share_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Konekte pou kontinye', response.data)
        self.assertEqual(BatchClick.query.count(), 0)

        login = c.post('/auth/login', data={
            'identifier': 'U1',
            'password': 'p',
            'next': share_url,
        })
        self.assertEqual(login.status_code, 302)
        self.assertEqual(login.location, share_url)
        page = c.get(login.location)
        self.assertEqual(page.status_code, 200)
        self.assertEqual(BatchClick.query.filter_by(referrer_whatsapp=REFERRER).count(), 1)

    def test_self_referral_is_not_counted_but_batch_renders(self):
        c = app.test_client()
        with c:
            c.post('/auth/login', data={'identifier': 'Admin509', 'password': 'ap'})
            response = c.get(_base_url(), environ_base={'REMOTE_ADDR': '8.8.8.8'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(BatchClick.query.count(), 0)

    def test_rewards_dashboard_uses_signed_links_and_real_click_counts(self):
        c = app.test_client()
        with c:
            c.post('/auth/login', data={'identifier': 'Admin509', 'password': 'ap'})
            page = c.get('/gkach/rewards/dashboard')
            self.assertEqual(page.status_code, 200)
            html = page.get_data(as_text=True)
            self.assertIn('/s/b/B1?ref=', html)
            self.assertIn('Lyen pataj pou gwoup B1', html)

            summary = c.get('/gkach/api/summary')
            self.assertEqual(summary.status_code, 200)
            self.assertEqual(summary.get_json()['total_clicks'], 0)

    def test_untrusted_forwarded_ip_cannot_spoof_blocked_ip(self):
        GkachService.set_blocked_ips(['9.9.9.9'])
        with app.test_request_context(
            '/s/b/B1',
            headers={'X-Forwarded-For': '9.9.9.9'},
            environ_overrides={'REMOTE_ADDR': '8.8.8.8'},
        ):
            clicker_ip = _get_client_ip()
        self.assertEqual(clicker_ip, '8.8.8.8')
        self.assertTrue(GkachService.track_batch_click(
            'B1', REFERRER, clicker_whatsapp='+50950000000', clicker_ip=clicker_ip,
        ))
        self.assertEqual(BatchClick.query.count(), 1)

    # ---------------- ADMIN (block/unblock IP) ----------------
    def test_admin_block_unblock_http(self):
        ca = app.test_client()
        with ca:
            ca.post('/auth/login', data={'identifier': 'Admin509',
                                         'password': 'ap'})
            self.assertEqual(ca.get('/admin/rewards').status_code, 200)
            with patch('app.services.notification_service.alert_admin') as mock_alert:
                ca.post('/admin/rewards/block-ip', data={'ip': '5.5.5.5'})
                mock_alert.assert_not_called()
            self.assertIn('5.5.5.5', GkachService.get_blocked_ips())

            # cliqueur depuis cette IP (device neuf) = ignoré
            c2 = app.test_client()
            with c2:
                c2.post('/auth/login', data={'identifier': 'U2', 'password': 'p'})
                c2.get(_base_url(), environ_base={'REMOTE_ADDR': '5.5.5.5'})
            self.assertEqual(BatchClick.query.count(), 0)

            # unblock
            with patch('app.services.notification_service.alert_admin') as mock_alert:
                ca.post('/admin/rewards/unblock-ip', data={'ip': '5.5.5.5'})
                mock_alert.assert_not_called()
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
