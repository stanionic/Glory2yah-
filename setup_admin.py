"""
Admin Setup Script for Glory2YahPub (STANDALONE)
Creates or updates the admin user to match current default ADMIN_* config
in app.config:

  ADMIN_PSEUDO   -> login identifier (default: +50942882076)
  ADMIN_WHATSAPP -> user.whatsapp
  ADMIN_NAME     -> user.name
  ADMIN_PASSWORD -> set_password(...) (default: StanGlory2YahPub1986)

Kept IDEMPOTENT: safe to re-run. Override values with env vars.
"""
import os
import sys
sys.path.insert(0, os.path.abspath('.'))

from app.models.user import User
from app.models.user_gkach import UserGkach
from app.models.ad import Ad
from app.models.delivery import Delivery
from app.models.batch import Batch
from app.models.batch_ad import BatchAd
from app.models.gkach_transaction import GkachTransaction

from app import create_app, db


def _resolve_admin_values(app):
    """Return (pseudo, whatsapp, name, password) using config or env fallbacks."""
    cfg = app.config
    fallback_wa = '+50942882076'

    whatsapp = (
        os.environ.get('ADMIN_WHATSAPP')
        or cfg.get('ADMIN_WHATSAPP')
        or fallback_wa
    )
    pseudo = (
        os.environ.get('ADMIN_PSEUDO')
        or cfg.get('ADMIN_PSEUDO')
        or whatsapp  # keep sync with default config.py: ADMIN_PSEUDO default = ADMIN_WHATSAPP
    )
    name = (
        os.environ.get('ADMIN_NAME')
        or cfg.get('ADMIN_NAME')
        or 'Glory2YahPub'
    )
    password = (
        os.environ.get('ADMIN_PASSWORD')
        or cfg.get('ADMIN_PASSWORD')
        or 'StanGlory2YahPub1986'
    )
    return pseudo, whatsapp, name, password


def setup_admin():
    app = create_app(os.environ.get('FLASK_ENV') or 'development')

    with app.app_context():
        db.create_all()
        pseudo, whatsapp, name, password = _resolve_admin_values(app)

        # Multi-lookup (idem pattern app/__init__.py bootstrap):
        #  1) whatsapp match  ->  2) pseudo match  ->  3) any is_admin=True
        admin = (
            User.query.filter(User.whatsapp == whatsapp).first()
            or User.query.filter(User.pseudo == pseudo).first()
            or User.query.filter_by(is_admin=True).first()
        )

        if admin:
            print("Updating existing admin user...")
        else:
            print("Creating new admin user...")
            admin = User(
                auth_provider='whatsapp',
            )
            db.session.add(admin)

        # IDEMPOTENT UPGRADE (same policy as in app/__init__.py bootstrap):
        admin.pseudo = pseudo
        admin.whatsapp = whatsapp
        admin.name = name
        admin.is_admin = True
        admin.is_active = True
        admin.auth_provider = 'whatsapp' if (admin.auth_provider or '') in (None, '', None) else (admin.auth_provider or 'whatsapp')
        if not admin.auth_provider:
            admin.auth_provider = 'whatsapp'
        # ALWAYS refresh password (sync guarantee with request)
        admin.set_password(password)

        db.session.flush()

        # Ensure linked UserGkach row (to avoid lookups null on gkach dashboard):
        if admin.id:
            ug = UserGkach.query.filter(
                (UserGkach.user_id == admin.id) | (UserGkach.user_whatsapp == admin.whatsapp)
            ).first()
            if not ug:
                db.session.add(UserGkach(
                    user_id=admin.id,
                    user_whatsapp=admin.whatsapp,
                    gkach_balance=0,
                ))

        db.session.commit()

        print("\nAdmin user setup complete!")
        print("=" * 60)
        print(f"Pseudo (login identifier): {pseudo}")
        print(f"WhatsApp:                    {whatsapp}")
        print(f"Name:                        {name}")
        print(f"Password:                    {password}")
        print(f"is_admin:                    {admin.is_admin}")
        print(f"is_active:                   {admin.is_active}")
        print("=" * 60)
        print("ℹ️  Rendre les valeurs différentes en PROD:")
        print("     set ADMIN_WHATSAPP=... ADMIN_PSEUDO=... ADMIN_NAME=... ADMIN_PASSWORD=...")
        print("     avant d'exécuter ce script.")


if __name__ == '__main__':
    setup_admin()
