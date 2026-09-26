import logging, re, io, json
logging.disable(logging.CRITICAL)
from app import create_app
app = create_app()
with app.test_client() as c:
    r = c.get('/auth/login')
    html = r.data.decode('utf-8', errors='ignore')
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    csrf = m.group(1) if m else ''
    r = c.post('/auth/login', data={'csrf_token': csrf, 'identifier': 'testuser', 'password': '123456'}, follow_redirects=False)
    print('Login:', r.status_code)
    r = c.get('/konferans/')
    html = r.data.decode('utf-8', errors='ignore')
    m = re.search(r'<meta name="csrf-token" content="([^"]+)"', html)
    csrf2 = m.group(1) if m else ''
    print('CSRF meta:', bool(csrf2))
    r = c.post('/konferans/create_room', data={'room_name': 'Test', 'is_private': 'false'}, headers={'X-CSRFToken': csrf2}, follow_redirects=False)
    print('Create:', r.status_code, r.data[:150])
    rd = json.loads(r.data)
    if rd.get('success'):
        rc = rd['room_code']
        print('Room:', rc)
        data = {'room_id': rc, 'user_name': 'Test'}
        data['media'] = (io.BytesIO(b'fake png'), 'test.png')
        r = c.post('/konferans/upload_media', data=data, content_type='multipart/form-data', headers={'X-CSRFToken': csrf2}, follow_redirects=False)
        print('Upload:', r.status_code, r.data[:200])
