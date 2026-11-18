"""The visible buttons that open the Wi-Fi zone: Sèvis menu, home hero, profile shortcut."""
import os
import re
import sys
import uuid

import pytest

os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('SECRET_KEY', 'uwz-tests-secret')
os.environ.setdefault('WTF_CSRF_ENABLED', 'False')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import create_app, db
from app.models.user import User


@pytest.fixture()
def app():
    a = create_app('testing')
    a.config['WTF_CSRF_ENABLED'] = False
    yield a
    with a.app_context():
        db.session.remove()
        db.drop_all()


def _login(app):
    with app.app_context():
        u = User(whatsapp='+5094' + str(uuid.uuid4().int)[:7], pseudo='b' + uuid.uuid4().hex[:10], name='B',
                 auth_provider='whatsapp', is_active=True)
        u.set_password('Str0ng-Passw0rd!')
        db.session.add(u)
        db.session.commit()
        uid = u.id
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(uid)
        s['_fresh'] = True
    return c


def _anchor(html, needle):
    """Return the <a ...> tag containing `needle`."""
    for m in re.finditer(r'<a\b[^>]*>', html):
        if needle in m.group(0):
            return m.group(0)
    return None


@pytest.mark.parametrize('logged_in', [False, True])
def test_home_page_has_a_wifi_zone_button_for_everyone(app, logged_in):
    c = _login(app) if logged_in else app.test_client()
    html = c.get('/').data.decode()
    tag = _anchor(html, 'id="wifiZoneBtn"')
    assert tag and 'href="/wifi/zone"' in tag and 'hero-btn secondary' in tag
    assert 'WI-FI ZONE' in html and '📶' in html
    assert 'KREYE PIBLISITE' in html and 'href="/submit_ad"' in html          # existing button untouched
    assert html.index('KREYE PIBLISITE') < html.index('WI-FI ZONE')            # primary action stays first


def test_profile_has_a_wifi_zone_shortcut_next_to_the_other_services(app):
    html = _login(app).get('/auth/profile').data.decode()
    cards = re.findall(r'<a href="([^"]+)" class="action-card">.*?<span class="action-label">([^<]+)</span>',
                       html, flags=re.S)
    labels = [l for _, l in cards]
    assert ('/wifi/zone', 'Wi-Fi Zone') in cards
    for existing in ('Bous', 'Livrezon', 'Konferans', 'Lekòl Biblik', 'Mennen M'):   # nothing was displaced
        assert existing in labels


def test_the_sevis_menu_entry_is_present_on_the_home_and_profile_pages(app):
    c = _login(app)
    for path in ('/', '/auth/profile'):
        html = c.get(path).data.decode()
        assert 'href="/wifi/zone"' in html and 'Rezo Entènèt' in html, path


def test_every_wifi_button_leads_to_a_working_page(app):
    c = _login(app)
    for path in ('/', '/auth/profile'):
        links = set(re.findall(r'href="(/wifi/zone)"', c.get(path).data.decode()))
        assert links == {'/wifi/zone'}
        r = c.get('/wifi/zone')
        assert r.status_code == 200 and 'Wi-Fi Zone' in r.data.decode()
    anon = app.test_client().get('/wifi/zone')                                   # public landing for visitors
    assert anon.status_code == 200 and 'Konekte pou kòmanse' in anon.data.decode()


def test_buttons_do_not_depend_on_the_wifi_blueprint_being_registered(app):
    """The links are plain paths (like the Sèvis menu), so the home and profile pages can never
    crash with a url_for BuildError if the optional Wi-Fi module failed to load."""
    html_home = app.test_client().get('/').data.decode()
    assert 'url_for' not in html_home and "wifi_ui" not in html_home
    assert _login(app).get('/auth/profile').status_code == 200
