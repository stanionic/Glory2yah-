import pytest
from app import create_app
from app.extensions import db
@pytest.fixture()
def app():
    a=create_app({"TESTING":True,"SQLALCHEMY_DATABASE_URI":"sqlite:///:memory:"})
    with a.app_context(): db.create_all()
    yield a
    with a.app_context(): db.drop_all()
@pytest.fixture()
def client(app): return app.test_client()
