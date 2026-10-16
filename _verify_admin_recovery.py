"""Verify admin bootstrap: (A) password NOT reset on normal boot,
(B) ADMIN_PASSWORD_RESET=1 force-resets it (break-glass). Uses temp SQLite."""
import os
import sys
import tempfile
import shutil

d = tempfile.mkdtemp()
dbp = os.path.join(d, "t.db")
os.environ["FLASK_ENV"] = "testing"
os.environ["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{dbp}"
os.environ["ADMIN_PASSWORD"] = "KnownAdminPass123!"
os.environ.pop("ADMIN_PASSWORD_RESET", None)

FAILS = []


def ck(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -> {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)


try:
    from app import create_app, db
    from app.models import User
    from werkzeug.security import check_password_hash

    # Boot 1: create admin
    app = create_app("testing")
    with app.app_context():
        a = User.query.filter_by(is_admin=True).first()
        ck("admin created on first boot", a is not None)
        ck("admin password == ADMIN_PASSWORD", a and check_password_hash(a.password_hash, "KnownAdminPass123!"))
        # admin changes password in-app
        a.set_password("MyOwnNewPass456!")
        db.session.commit()
        h_after_change = a.password_hash

    # Boot 2: normal boot (no reset) -> password MUST persist
    app2 = create_app("testing")
    with app2.app_context():
        a2 = User.query.filter_by(is_admin=True).first()
        ck("password NOT reset on normal boot (security preserved)",
           a2.password_hash == h_after_change)

    # Boot 3: break-glass reset -> password forced back to ADMIN_PASSWORD
    os.environ["ADMIN_PASSWORD_RESET"] = "1"
    app3 = create_app("testing")
    with app3.app_context():
        a3 = User.query.filter_by(is_admin=True).first()
        ck("break-glass ADMIN_PASSWORD_RESET=1 force-resets password",
           check_password_hash(a3.password_hash, "KnownAdminPass123!"))
    os.environ["ADMIN_PASSWORD_RESET"] = "0"

    print("-" * 60)
    print("RESULT:", "ALL PASS" if not FAILS else f"FAILED: {FAILS}")
    sys.exit(2 if FAILS else 0)
finally:
    shutil.rmtree(d, ignore_errors=True)
