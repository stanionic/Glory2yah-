"""Local smoke test for the one-shot admin DB migration page."""
import io
import os

from app import create_app, db
from app.models import User

app = create_app()
app.config['WTF_CSRF_ENABLED'] = False
app.config['TESTING'] = True

ADMIN_WA = '+50990000999'
SRC = os.path.join('instance', 'glory2yahpub_dev.db')

fails = []


def check(name, cond):
    print(('  [OK]  ' if cond else '  [FAIL] ') + name)
    if not cond:
        fails.append(name)


with app.app_context():
    User.query.filter_by(whatsapp=ADMIN_WA).delete()
    db.session.commit()
    admin = User(name='DbMig Admin', pseudo='DbMigAdmin', whatsapp=ADMIN_WA,
                 password_hash='x', is_admin=True)
    db.session.add(admin)
    db.session.commit()
    admin_id = admin.id

# start from a clean snapshot folder so the assertions are deterministic
_mig_dir = os.path.join(app.config.get('INSTANCE_DIR') or 'instance', 'db_migration')
if os.path.isdir(_mig_dir):
    import shutil
    shutil.rmtree(_mig_dir, ignore_errors=True)

with app.test_client() as c:
    with c.session_transaction() as s:
        s['_user_id'] = str(admin_id)
        s['_fresh'] = True

    r = c.get('/admin/db-migration')
    check('GET page -> 200', r.status_code == 200)
    body = r.get_data(as_text=True)
    check('page shows target dialect guard', 'PA PostgreSQL' in body or 'PostgreSQL' in body)
    check('page has upload form', 'admin_db.upload' in body or '/admin/db-migration/upload' in body)

    with open(SRC, 'rb') as fh:
        payload = fh.read()
    r = c.post('/admin/db-migration/upload',
               data={'snapshot': (io.BytesIO(payload), 'smoke_dev.db')},
               content_type='multipart/form-data')
    check('upload -> 302', r.status_code == 302)

    folder = os.path.join(app.config.get('INSTANCE_DIR') or 'instance', 'db_migration')
    names = sorted(n for n in os.listdir(folder) if n.endswith('smoke_dev.db')) if os.path.isdir(folder) else []
    check('snapshot stored on disk', len(names) == 1)
    snap = names[0] if names else None

    if snap:
        r = c.post('/admin/db-migration/run',
                   data={'snapshot': snap, 'dry_run': '1'})
        check('dry-run -> 200', r.status_code == 200)
        txt = r.get_data(as_text=True)
        import re as _re
        nums = _re.findall(r'TOTAL\s+(\d+)\s+rows across\s+(\d+)\s+tables', txt)
        check('dry-run reports 73 tables', bool(nums) and nums[0][1] == '73')
        check('dry-run reports rows > 0', bool(nums) and int(nums[0][0]) > 0)

        r = c.post('/admin/db-migration/run',
                   data={'snapshot': snap, 'confirm': 'MIGRATE'})
        check('real run blocked on non-postgres target', r.status_code == 302)

        r = c.post('/admin/db-migration/run', data={'snapshot': '../evil.db', 'dry_run': '1'})
        check('traversal rejected', r.status_code == 302)

# Guest must be bounced. This MUST run outside the `with app.test_client()` block:
# that block preserves the request/app context, so `current_user` from the admin
# request would leak into the "guest" client and yield a false 200.
_guest = app.test_client()
_rg = _guest.get('/admin/db-migration')
check('guest blocked (302/401/403)', _rg.status_code in (302, 401, 403))

print('\nALL DB-MIGRATION SMOKE TESTS PASSED' if not fails else f'\nFAILED: {fails}')
