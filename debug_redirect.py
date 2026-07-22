"""Debug script to identify redirect loop"""
import sys
sys.path.insert(0, '.')
from app import create_app
app = create_app('development')

with app.test_client() as client:
    # Test 1: Visit ecole_biblique index without auth
    print('=== Test 1: GET /ecole_biblique/ (no auth) ===')
    resp = client.get('/ecole_biblique/', follow_redirects=False)
    print(f'Status: {resp.status_code}')
    print(f'Location: {resp.headers.get("Location", "none")}')
    
    # Test 2: Visit main index without auth
    print('\n=== Test 2: GET / (no auth) ===')
    resp = client.get('/', follow_redirects=False)
    print(f'Status: {resp.status_code}')
    print(f'Location: {resp.headers.get("Location", "none")}')
    
    # Test 3: Visit auth login without auth
    print('\n=== Test 3: GET /auth/login (no auth) ===')
    resp = client.get('/auth/login', follow_redirects=False)
    print(f'Status: {resp.status_code}')
    print(f'Location: {resp.headers.get("Location", "none")}')
    
    # Test 4: Follow redirect from login to check loop
    print('\n=== Test 4: GET /auth/login with follow_redirects to trace chain ===')
    resp = client.get('/auth/login', follow_redirects=True)
    print(f'Final status: {resp.status_code}')
    print(f'Final URL: {resp.request.url}')
    
    # Test 5: Test registration page access
    print('\n=== Test 5: GET /ecole_biblique/register (no auth) ===')
    resp = client.get('/ecole_biblique/register', follow_redirects=False)
    print(f'Status: {resp.status_code}')
    print(f'Location: {resp.headers.get("Location", "none")}')
    
    # Test 6: Trace the redirect chain for a protected route
    print('\n=== Test 6: Protected route /ecole_biblique/student ===')
    resp = client.get('/ecole_biblique/student', follow_redirects=False)
    print(f'Status: {resp.status_code}')
    print(f'Location: {resp.headers.get("Location", "none")}')
    
    # Test 7: Trace full redirect chain for ecole_biblique/student
    print('\n=== Test 7: Full chain for /ecole_biblique/student ===')
    resp = client.get('/ecole_biblique/student', follow_redirects=True)
    print(f'Final status: {resp.status_code}')
    print(f'Final URL: {resp.request.url}')
    print(f'Total redirects: {len(resp.history)}')
    for h in resp.history:
        print(f'  {h.status_code} -> {h.headers.get("Location")}')
    
    # Test 8: Try login POST and trace redirect
    print('\n=== Test 8: POST /auth/login with test user ===')
    resp = client.post('/auth/login', data={
        'identifier': '+50912345678',
        'password': '123456'
    }, follow_redirects=False)
    print(f'Status: {resp.status_code}')
    print(f'Location: {resp.headers.get("Location", "none")}')
    print(f'Set-Cookie: {resp.headers.get("Set-Cookie", "none")}')
    
    # Test 9: Follow login redirect to check if it redirects to login page again
    if resp.status_code == 302 and resp.headers.get("Location"):
        print(f'\n=== Test 9: Following login redirect to {resp.headers.get("Location")} ===')
        resp2 = client.get(resp.headers.get("Location"), follow_redirects=False)
        print(f'Status: {resp2.status_code}')
        print(f'Location: {resp2.headers.get("Location", "none")}')
        if resp2.status_code == 302:
            resp3 = client.get(resp2.headers.get("Location"), follow_redirects=False)
            print(f'  Follow again -> Status: {resp3.status_code}, Location: {resp3.headers.get("Location", "none")}')
    
    # Test 10: Check if login then ecole_biblique works
    print('\n=== Test 10: Login + visit /ecole_biblique/ ===')
    client.post('/auth/login', data={
        'identifier': '+50912345678',
        'password': '123456'
    })
    resp = client.get('/ecole_biblique/', follow_redirects=False)
    print(f'After login -> /ecole_biblique/: Status {resp.status_code}, Location: {resp.headers.get("Location", "none")}')
    
    # Test 11: Create a fresh user and test full flow
    print('\n=== Test 11: Register new test user ===')
    # First create a fresh test user in main app
    from app.models.user import User
    from app.models.user_gkach import UserGkach
    
    # Delete if exists
    existing = User.query.filter_by(pseudo='test_admission').first()
    if existing:
        UserGkach.query.filter_by(user_id=existing.id).delete()
        # Delete EcoleUser linked to this whatsapp
        ecole_existing = EcoleUser.query.filter_by(whatsapp='+50999999999').first()
        if ecole_existing:
            db.session.delete(ecole_existing)
        db.session.delete(existing)
        db.session.commit()
    
    # Create main user
    test_user = User(
        whatsapp='+50999999999',
        pseudo='test_admission',
        name='Test User',
        auth_provider='whatsapp',
        is_active=True
    )
    test_user.set_password('test123456')
    db.session.add(test_user)
    db.session.flush()
    
    user_gkach = UserGkach(
        user_id=test_user.id,
        user_whatsapp='+50999999999',
        gkach_balance=0
    )
    db.session.add(user_gkach)
    db.session.commit()
    
    print(f'Created test user: {test_user.id}, {test_user.pseudo}')
    
    # Login as this user
    print('\n=== Test 11b: Login as test user ===')
    resp = client.post('/auth/login', data={
        'identifier': 'test_admission',
        'password': 'test123456'
    }, follow_redirects=False)
    print(f'Login status: {resp.status_code}')
    print(f'Login Location: {resp.headers.get("Location", "none")}')
    print(f'Set-Cookie: {resp.headers.get("Set-Cookie", "none")}')
    
    # Follow redirects to trace
    print('\n=== Test 11c: Follow login redirect chain ===')
    current_url = '/auth/login'
    max_loops = 5
    for i in range(max_loops):
        resp = client.get(current_url, follow_redirects=False)
        print(f'  {i}: GET {current_url} -> Status {resp.status_code}, Location: {resp.headers.get("Location", "none")}')
        if resp.status_code == 302:
            loc = resp.headers.get("Location", "")
            if loc.startswith('/'):
                current_url = loc
            else:
                print(f'  Redirect to external: {loc}')
                break
        else:
            print(f'  Rendered page (no redirect)')
            break
        if i == max_loops - 1:
            print(f'  WARNING: Possible redirect loop detected!')
    
    # Test 12: Now visit ecole_biblique as logged-in user
    print('\n=== Test 12: Visit /ecole_biblique/ after login ===')
    resp = client.get('/ecole_biblique/', follow_redirects=False)
    print(f'Status: {resp.status_code}')
    print(f'Location: {resp.headers.get("Location", "none")}')
    # Follow redirect
    if resp.status_code == 302:
        loc = resp.headers.get("Location", "")
        print(f'  Following to: {loc}')
        for i in range(5):
            resp = client.get(loc if loc.startswith('/') else '/', follow_redirects=False)
            print(f'  {i}: Status {resp.status_code}, Location: {resp.headers.get("Location", "none")}')
            if resp.status_code == 302:
                loc = resp.headers.get("Location", "")
                if not loc.startswith('/'):
                    break
            else:
                print(f'  Final page loaded (status {resp.status_code})')
                break
