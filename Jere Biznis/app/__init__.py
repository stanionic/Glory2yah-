import os
from flask import Flask
from .extensions import db

def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY", "dev-change-me"),
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL", "sqlite:///glory2yahpub_institution.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        INSTITUTION_MONTHLY_PRICE_GKACH=int(os.getenv("INSTITUTION_MONTHLY_PRICE_GKACH", "500")),
        TRIAL_DURATION_DAYS=int(os.getenv("TRIAL_DURATION_DAYS", "30")),
        GRACE_PERIOD_DAYS=int(os.getenv("GRACE_PERIOD_DAYS", "7")),
    )
    if test_config:
        app.config.update(test_config)
    db.init_app(app)
    from .routes import api, web
    app.register_blueprint(api, url_prefix="/api/v1")
    app.register_blueprint(web)
    with app.app_context():
        db.create_all()
    return app
