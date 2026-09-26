"""Smoke test: Flask uploads routes + persistence banner.

Validates:
  1. GET /uploads/test_smoke.jpg → 200 from instance/uploads (UPLOAD_FOLDER)
  2. GET /static/uploads/test_smoke.jpg → 200 via before_request fallback
  3. GET /uploads/nonexistent.jpg → 404
  4. Path traversal protection → 404
  5. Startup banner logs don't crash app creation
"""
import os
import sys
import tempfile
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

# --- Create a fake test image in BOTH candidate locations
tmp_cleanup = []

def _touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb')
    tmp_cleanup.append(path)


def cleanup():
    for p in tmp_cleanup:
        try:
            if os.path.isfile(p): os.remove(p)
        except Exception:
            pass


def main():
    # 1) Use TestingConfig but OVERRIDE UPLOAD_FOLDER to a tmp directory with our file
    # Create tmp instance/uploads simulating Render persistent disk
    tmp_instance = tempfile.mkdtemp(prefix='g2y_smoke_')
    tmp_uploads = os.path.join(tmp_instance, 'uploads')
    os.makedirs(tmp_uploads, exist_ok=True)
    tmp_cleanup.append(tmp_instance)  # whole dir cleanup

    # Write fake image
    test_img = os.path.join(tmp_uploads, 'test_smoke.jpg')
    with open(test_img, 'wb') as f:
        f.write(b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb')

    # Also create matching folder locally for legacy static/uploads
    legacy_static_uploads = os.path.join(HERE, 'static', 'uploads')
    os.makedirs(legacy_static_uploads, exist_ok=True)
    # Don't place test_smoke.jpg in legacy -> forces fallback to persistent
    print(f'[TEST] tmp_uploads = {tmp_uploads}')
    print(f'[TEST] test_img exists = {os.path.isfile(test_img)}')

    # --- Environment: force TestingConfig but override UPLOAD_FOLDER
    os.environ['UPLOAD_FOLDER'] = tmp_uploads
    os.environ['FLASK_ENV'] = 'testing'
    # Ensure TESTING uses in-memory sqlite; avoid DB migrations
    os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    # Prevent DB init issues: create_app() bootstrap might need SECRET_KEY
    os.environ['SECRET_KEY'] = 'test-smoke-uploads-123'

    try:
        from app import create_app
        app = create_app('testing')
        # Override config (some settings post-create_app
        app.config['TESTING'] = True
        app.config['UPLOAD_FOLDER'] = tmp_uploads
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['SERVER_NAME'] = 'localhost.localdomain'

        print('[TEST] create_app OK, UPLOAD_FOLDER =', app.config['UPLOAD_FOLDER'])

        # --- Flask test client
        with app.test_client() as c:
            # 1) Canonical /uploads/<filename>
            r1 = c.get('/uploads/test_smoke.jpg')
            print(f'[TEST 1] GET /uploads/test_smoke.jpg = {r1.status_code} (expect 200)')
            assert r1.status_code == 200, f'/uploads/test_smoke.jpg: expected 200 got {r1.status_code}'
            assert r1.content_type in ('image/jpeg', 'application/octet-stream'), f'content_type = {r1.content_type}'
            assert len(r1.data) > 10, f'too few bytes: {len(r1.data)}'

            # 2) /static/uploads/<filename> (before_request fallback)
            r2 = c.get('/static/uploads/test_smoke.jpg')
            print(f'[TEST 2] GET /static/uploads/test_smoke.jpg = {r2.status_code} (expect 200)')
            assert r2.status_code == 200, f'/static/uploads/test_smoke.jpg: expected 200 got {r2.status_code}'

            # 3) Nonexistent
            r3 = c.get('/uploads/nope_xyz_123.jpg')
            print(f'[TEST 3] GET /uploads/nope_xyz_123.jpg = {r3.status_code} (expect 404)')
            assert r3.status_code == 404, f'expected 404 got {r3.status_code}'

            # 4) Path traversal protection
            r4 = c.get('/uploads/../instance/../etc/passwd')
            print(f'[TEST 4] GET /uploads/../etc/passwd = {r4.status_code} (expect 404 or 308→404)')
            assert r4.status_code in (404, 308, 400, 301), f'traversal not blocked: {r4.status_code}'

            # 5) static/uploads traversal
            r5 = c.get('/static/uploads/../../../etc/passwd')
            print(f'[TEST 5] GET /static/uploads/../../../etc/passwd = {r5.status_code} (expect 404)')
            assert r5.status_code in (404, 308, 400, 301), f'traversal static not blocked: {r5.status_code}'

            print()
            print('ALL 5 SMOKE TESTS PASSED ✅')
            return 0
    except AssertionError as ae:
        print(f'❌ FAILURE: {ae}')
        import traceback; traceback.print_exc()
        return 1
    except Exception as e:
        print(f'💥 CRASH: {e}')
        import traceback; traceback.print_exc()
        return 2
    finally:
        # cleanup whole tmp dir tree
        try:
            shutil.rmtree(tmp_instance, ignore_errors=True)
        except Exception:
            pass


if __name__ == '__main__':
    sys.exit(main())
