"""Debug script to find the ecole biblique Internal Server Error"""
import sys
import os
import traceback

project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from app import app, db

print("=" * 60)
print("ECOLE BIBLIQUE DEBUG")
print("=" * 60)

with app.test_client() as c:
    # Step 1: Login as test user
    print("\n[1] Logging in as test user...")
    r = c.post('/auth/login', data={'whatsapp': '+50912345678', 'password': '123456'}, follow_redirects=False)
    print(f"    Login status: {r.status_code}")
    if r.status_code == 302:
        print(f"    Redirect to: {r.headers.get('Location')}")

    # Step 2: Try ecole biblique index
    print("\n[2] Accessing /ecole_biblique/ ...")
    r2 = c.get('/ecole_biblique/')
    print(f"    Status: {r2.status_code}")
    if r2.status_code == 500:
        print(f"    500 ERROR BODY: {r2.data.decode()[:3000]}")
    elif r2.status_code == 302:
        print(f"    Redirect to: {r2.headers.get('Location')}")
        # Follow redirect
        loc = r2.headers.get('Location')
        if loc:
            r3 = c.get(loc)
            print(f"    After redirect - Status: {r3.status_code}")
            if r3.status_code == 500:
                print(f"    500 ERROR BODY: {r3.data.decode()[:3000]}")
            elif r3.status_code == 302:
                print(f"    Another redirect to: {r3.headers.get('Location')}")
    else:
        print(f"    Response: {r2.data.decode()[:500]}")

    # Step 3: Try register page directly
    print("\n[3] Accessing /ecole_biblique/register ...")
    r4 = c.get('/ecole_biblique/register')
    print(f"    Status: {r4.status_code}")
    if r4.status_code == 500:
        print(f"    500 ERROR BODY: {r4.data.decode()[:3000]}")
    else:
        print(f"    Response: {r4.data.decode()[:300]}")

    # Step 4: Try modules page
    print("\n[4] Accessing /ecole_biblique/modules ...")
    r5 = c.get('/ecole_biblique/modules')
    print(f"    Status: {r5.status_code}")
    if r5.status_code == 500:
        print(f"    500 ERROR BODY: {r5.data.decode()[:3000]}")

    # Step 5: Check app error logs
    print("\n[5] Checking app_error.txt...")
    error_file = os.path.join(project_root, 'app_error.txt')
    if os.path.exists(error_file):
        with open(error_file, 'r') as f:
            content = f.read()
        print(f"    app_error.txt exists, {len(content)} bytes")
        print(f"    Last 500 chars: {content[-500:]}")
    else:
        print("    app_error.txt does not exist")

    # Step 6: Check if debug mode is on and show traceback
    print("\n[6] App debug mode:", app.debug)

print("\n" + "=" * 60)
print("DEBUG COMPLETE")
print("=" * 60)
