import logging, re, io, sys, os
logging.disable(logging.CRITICAL)

from app import create_app

app = create_app()
with app.test_client() as c:
    # Get CSRF token
    r = c.get('/auth/login')
    html = r.data.decode('utf-8', errors='ignore')
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    csrf = m.group(1) if m else ''
    print('CSRF found:', bool(csrf))
    
    # Login
    r = c.post('/auth/login', data={'csrf_token': csrf, 'identifier': 'testuser', 'password': '123456'}, follow_redirects=False)
    print('Login:', r.status_code)
    
    # Get CSRF token from meta tag on konferans page
    r = c.get('/konferans/')
    html = r.data.decode('utf-8', errors='ignore')
    m = re.search(r'<meta name="csrf-token" content="([^"]+)"', html)
    csrf2 = m.group(1) if m else ''
    print('CSRF meta found:', bool(csrf2))
    
    # Upload a test image
    data = {'room_id': 'EE8327', 'user_name': 'Test', 'csrf_token': csrf2}
    data['media'] = (io.BytesIO(b'fake png data for testing'), 'test_image.png')
    r = c.post('/konferans/upload_media', data=data, content_type='multipart/form-data', follow_redirects=False)
    print('Upload:', r.status_code, r.data[:300])
    
    if r.status_code == 200:
        print('SUCCESS!')
    elif r.status_code == 303:
        print('REDIRECT - CSRF may have failed')
