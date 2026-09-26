import os
from datetime import date, timedelta

import pytest

os.environ.setdefault("FLASK_ENV", "testing")
os.environ.setdefault("SECRET_KEY", "party-module-tests-secret")
os.environ.setdefault("WTF_CSRF_ENABLED", "False")

from app import create_app, db
from app.models.party import Party, PartyParticipant


@pytest.fixture()
def app():
    application = create_app("testing")
    application.config["WTF_CSRF_ENABLED"] = False
    with application.app_context():
        db.create_all()
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def test_public_page_does_not_expose_participant_contact(app, client):
    with app.app_context():
        party = Party(
            name="Public event",
            date=date.today() + timedelta(days=3),
            owner_code="ABC123",
        )
        db.session.add(party)
        db.session.flush()
        db.session.add(
            PartyParticipant(
                party_id=party.party_id,
                name="Private person",
                whatsapp="+50900000000",
            )
        )
        db.session.commit()
        party_id = party.party_id

    response = client.get(f"/fet/{party_id}")
    assert response.status_code == 200
    assert b"Private person" not in response.data
    assert b"+50900000000" not in response.data
    assert b"Moun ki Enskri (1)" in response.data


def test_past_event_rejects_registration(app, client):
    with app.app_context():
        party = Party(
            name="Past event",
            date=date.today() - timedelta(days=1),
            owner_code="ABC123",
        )
        db.session.add(party)
        db.session.commit()
        party_id = party.party_id

    response = client.post(
        f"/fet/register/{party_id}",
        data={"name": "Person", "whatsapp": "+50900000000"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    with app.app_context():
        assert PartyParticipant.query.count() == 0


def test_owner_export_requires_owner_session(app, client):
    with app.app_context():
        party = Party(
            name="Export event",
            date=date.today() + timedelta(days=3),
            owner_code="ABC123",
        )
        db.session.add(party)
        db.session.commit()
        party_id = party.party_id

    denied = client.get(f"/fet/admin/party/{party_id}/export.csv")
    assert denied.status_code in (302, 403)

    with client.session_transaction() as session:
        session[f"party_owner_{party_id}"] = True
    allowed = client.get(f"/fet/admin/party/{party_id}/export.csv")
    assert allowed.status_code == 200
    assert allowed.mimetype == "text/csv"
    assert b"WhatsApp" in allowed.data
