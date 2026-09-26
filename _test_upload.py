import logging
logging.disable(logging.CRITICAL)
from app import create_app
import os, tempfile, re

app = create_app()
with app.test_client() as c:
    # Get CSRF token from a page
    r = c.get('/konferans/')
    html = r.data.decode()
    m = re.search(r'name="csrf-token" content="([^"]+)', html)
    csrf = m.group(1) if m else 'missing'
    print('CSRF token:', csrf[:50])
    # Login with CSRF
    r = c.post('/auth/login', data={'identifier':'testuser','password':'123456', 'csrf_token': csrf}, follow_redirects=False)
    print('Login status:', r.status_code)
    # Upload
    with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as f:
        f.write(b'Test media file')
        tmpfile = f.name
    with open(tmpfile, 'rb') as f:
        r = c.post('/konferans/upload_media', data={'media': (f, 'test.txt'), 'room_id': 'EE8327', 'user_name': 'Test', 'csrf_token': csrf}, content_type='multipart/form-data', follow_redirects=False)
    print('Upload status:', r.status_code)
    print('Response:', r.data.decode()[:500])
    os.unlink(tmpfile)