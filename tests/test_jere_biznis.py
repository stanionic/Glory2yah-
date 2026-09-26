"""Tests for the Jere Biznis vitrine module (auto-admin + co-admins).

Run:
    python -m pytest tests/test_jere_biznis.py -q
"""
import os

os.environ.setdefault("FLASK_ENV", "testing")
os.environ.setdefault("SECRET_KEY", "jere-biznis-tests-secret")
os.environ.setdefault("WTF_CSRF_ENABLED", "False")

import pytest

from app import create_app, db
from app.models.jere_biznis import JereBiznisAdmin, JereBiznisLandingPage
from app.models.user import User


@pytest.fixture()
def app():
    a = create_app("testing")
    with a.app_context():
        db.create_all()
    yield a
    with a.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def _make_user(app, pseudo, whatsapp):
    with app.app_context():
        u = User(pseudo=pseudo, whatsapp=whatsapp, name=pseudo, is_active=True)
        db.session.add(u)
        db.session.commit()
        return u.id  # capture id while the instance is still attached


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def _create_vitrine(client, name="Lekòl Lespwa"):
    return client.post(
        "/jere-biznis/api/landing-pages",
        json={
            "business_name": name,
            "business_type": "school",
            "description": "Sèvis bon jan.",
            "phone": "+50900000000",
            "address": "Pòtoprens",
        },
    )


def test_creator_is_auto_owner(app, client):
    owner = _make_user(app, "met_kay", "+50910000001")
    _login(client, owner)
    r = _create_vitrine(client)
    assert r.status_code == 201
    data = r.get_json()
    assert data["role"] == "OWNER"
    assert data["admins_count"] == 1

    with app.app_context():
        page = db.session.get(JereBiznisLandingPage, data["id"])
        assert page.owner_user_id == str(owner.id)
        row = JereBiznisAdmin.query.filter_by(
            landing_page_id=page.id, user_id=str(owner), active=True
        ).first()
        assert row is not None and row.role == JereBiznisAdmin.ROLE_OWNER


def test_list_shows_my_pages(client):
    owner = _make_user(client.application, "list_owner", "+50910000002")
    _login(client, owner)
    _create_vitrine(client, "Magazen Bon Jan")
    _create_vitrine(client, "Legliz Betel")

    r = client.get("/jere-biznis/api/landing-pages")
    assert r.status_code == 200
    pages = r.get_json()
    assert len(pages) == 2
    assert {p["business_name"] for p in pages} == {"Magazen Bon Jan", "Legliz Betel"}
    assert all(p["role"] == "OWNER" for p in pages)


def test_owner_can_add_co_admin(app, client):
    owner = _make_user(app, "owner_add", "+50910000003")
    helper = _make_user(app, "helper_add", "+50910000004")
    _login(client, owner)
    pid = _create_vitrine(client).get_json()["id"]

    r2 = client.post(
        f"/jere-biznis/api/landing-pages/{pid}/admins",
        json={"pseudo": "helper_add"},
    )
    assert r2.status_code == 201
    admins = r2.get_json()
    assert any(
        a["user_id"] == str(helper) and a["role"] == "CO_ADMIN" for a in admins
    )


def test_co_admin_can_edit_but_not_delete_or_manage(app, client):
    owner = _make_user(app, "owner_perm", "+50910000005")
    helper = _make_user(app, "helper_perm", "+50910000006")
    _login(client, owner)
    pid = _create_vitrine(client).get_json()["id"]
    client.post(
        f"/jere-biznis/api/landing-pages/{pid}/admins", json={"pseudo": "helper_perm"}
    )

    _login(client, helper)
    r_edit = client.put(
        f"/jere-biznis/api/landing-pages/{pid}",
        json={"business_name": "Lekòl Nouvèl", "business_type": "school"},
    )
    assert r_edit.status_code == 200
    assert r_edit.get_json()["business_name"] == "Lekòl Nouvèl"

    r_del = client.delete(f"/jere-biznis/api/landing-pages/{pid}")
    assert r_del.status_code == 403

    r_add = client.post(
        f"/jere-biznis/api/landing-pages/{pid}/admins", json={"pseudo": "x"}
    )
    assert r_add.status_code == 403


def test_non_admin_forbidden(app, client):
    owner = _make_user(app, "owner_forb", "+50910000007")
    stranger = _make_user(app, "stranger", "+50910000008")
    _login(client, owner)
    pid = _create_vitrine(client).get_json()["id"]

    _login(client, stranger)
    r = client.get(f"/jere-biznis/api/landing-pages/{pid}")
    assert r.status_code == 403


def test_owner_cannot_remove_owner(app, client):
    owner = _make_user(app, "owner_self", "+50910000009")
    _login(client, owner)
    pid = _create_vitrine(client).get_json()["id"]

    r = client.delete(f"/jere-biznis/api/landing-pages/{pid}/admins/{owner}")
    assert r.status_code == 400


def test_owner_can_remove_co_admin(app, client):
    owner = _make_user(app, "owner_rem", "+50910000010")
    helper = _make_user(app, "helper_rem", "+50910000011")
    _login(client, owner)
    pid = _create_vitrine(client).get_json()["id"]
    client.post(
        f"/jere-biznis/api/landing-pages/{pid}/admins", json={"pseudo": "helper_rem"}
    )

    r = client.delete(f"/jere-biznis/api/landing-pages/{pid}/admins/{helper}")
    assert r.status_code == 200

    admins = client.get(f"/jere-biznis/api/landing-pages/{pid}/admins").get_json()
    assert str(helper) not in [a["user_id"] for a in admins]

    # The removed helper no longer sees the page in his list.
    _login(client, helper)
    pages = client.get("/jere-biznis/api/landing-pages").get_json()
    assert str(pid) not in [str(p["id"]) for p in pages]


def test_duplicate_co_admin_conflict(app, client):
    owner = _make_user(app, "owner_dup", "+50910000012")
    helper = _make_user(app, "helper_dup", "+50910000013")
    _login(client, owner)
    pid = _create_vitrine(client).get_json()["id"]
    client.post(
        f"/jere-biznis/api/landing-pages/{pid}/admins", json={"pseudo": "helper_dup"}
    )
    r = client.post(
        f"/jere-biznis/api/landing-pages/{pid}/admins", json={"pseudo": "helper_dup"}
    )
    assert r.status_code == 409


def test_status_announces_500_and_count(client):
    owner = _make_user(client.application, "status_owner", "+50910000014")
    _login(client, owner)

    r = client.get("/jere-biznis/api/status")
    assert r.status_code == 200
    data = r.get_json()
    assert data["monthly_price_gkach"] == 500
    assert data["landing_pages_count"] == 0
    assert data["reminder"]["status"] == "NO_PAGE"