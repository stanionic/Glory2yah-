"""Correct admin bootstrap test — ONE boot PER PROCESS (real reboot isolation).

Why a subprocess per boot: calling create_app() twice in one process shares the
module-level db + runs the import-time `app = create_app()`, which re-triggers
the bootstrap and muddies the "not reset on boot" guarantee. A fresh process is
the only faithful simulation of a Render redeploy.

Usage:
  _verify_admin_recovery2.py setup    # create admin (ADMIN_PASSWORD=...), then set a NEW pw
  _verify_admin_recovery2.py read     # boot only; print whether KNOWN and NEW pw validate
  _verify_admin_recovery2.py readreset# same, but with ADMIN_PASSWORD_RESET=1
"""
import os
import sys
import logging

MODE = sys.argv[1] if len(sys.argv) > 1 else ""
DBDIR = os.environ["_ADMTEST_DBDIR"]

os.environ["FLASK_ENV"] = "development"  # dev allows SQLite; admin bootstrap logic is identical
os.environ["DEV_DATABASE_URL"] = f"sqlite:///{os.path.join(DBDIR, 'adm.db')}"
os.environ.pop("DATABASE_URL", None)  # ensure dev path, not the PG-only production guard
os.environ.setdefault("SECRET_KEY", "admui-test-secret-key-0123456789abcdef")
os.environ["ADMIN_PASSWORD"] = "KnownAdminPass123!"
os.environ.pop("ADMIN_PASSWORD_RESET", None)
logging.disable(logging.CRITICAL)  # silence app bootstrap logs for a clean RESULT line

from app import create_app, db  # noqa: E402
from app.models import User  # noqa: E402
from werkzeug.security import check_password_hash  # noqa: E402


def _admin():
    app = create_app("development")
    with app.app_context():
        u = User.query.filter_by(is_admin=True).first()
        return u


def _validate(pw):
    app = create_app("development")
    with app.app_context():
        u = User.query.filter_by(is_admin=True).first()
        return bool(u and check_password_hash(u.password_hash, pw))


if MODE == "setup":
    u = _admin()
    assert u is not None, "admin not created"
    assert _validate("KnownAdminPass123!"), "admin pw != ADMIN_PASSWORD at creation"
    # simulate the admin changing their own password in-app
    app = create_app("development")
    with app.app_context():
        u = User.query.filter_by(is_admin=True).first()
        u.set_password("MyOwnNewPass456!")
        db.session.commit()
    print("SETUP_OK")

elif MODE == "read":
    # Normal reboot: NEW password must still work, ADMIN_PASSWORD must NOT.
    new_ok = _validate("MyOwnNewPass456!")
    known_ok = _validate("KnownAdminPass123!")
    print(f"READ new_ok={new_ok} known_ok={known_ok}")
    print("RESULT " + ("PASS" if (new_ok and not known_ok) else "FAIL"))

elif MODE == "readreset":
    os.environ["ADMIN_PASSWORD_RESET"] = "1"
    known_ok = _validate("KnownAdminPass123!")
    print(f"READRESET known_ok={known_ok}")
    print("RESULT " + ("PASS" if known_ok else "FAIL"))
