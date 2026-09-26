import logging, re, io, sys, os, json
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
    
    # Create a room
    r = c.post('/konferans/api/create_room', data={'room_name': 'Test Room', 'is_private': 'false'}, follow_redirects=False)
    print('Create room:', r.status_code, r.data[:200])
    
    room_data = json.loads(r.data)
    if room_data.get('success'):
        room_code = room_data['room_code']
        print('Room code:', room_code)
        
        # Get CSRF token from meta tag
        r = c.get('/konferans/')
        html = r.data.decode('utf-8', errors='ignore')
        m = re.search(r'<meta name="csrf-token" content="([^"]+)"', html)
        csrf2 = m.group(1) if m else ''
        print('CSRF meta found:', bool(csrf2))
        
        # Upload a test image
        data = {'room_id': room_code, 'user_name': 'Test', 'csrf_token': csrf2}
        data['media'] = (io.BytesIO(b'fake png data for testing'), 'test_image.png')
        r = c.post('/konferans/upload_media', data=data, content_type='multipart/form-data', follow_redirects=False)
        print('Upload:', r.status_code, r.data[:300])
    else:
        print('Room creation failed:', room_data)
