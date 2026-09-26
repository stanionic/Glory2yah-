#!/usr/bin/env python
"""Simple KONFERANS feature tests"""
import os
import sys
os.environ['FLASK_ENV'] = 'test'

print("\n[KONFERANS FEATURE TESTS]")
print("=" * 60)

# Test 1: Import and basic setup
print("\nTest 1: Imports & Setup")
try:
    from app import create_app, db
    from app.models.konferans import KonferansRoom, KonferansRecording
    from konferans.routes import FREE_MINUTES_DEFAULT, GKACH_PER_HOUR_DEFAULT
    print("  [OK] All imports successful")
except Exception as e:
    print(f"  [FAIL] Import error: {e}")
    sys.exit(1)

# Test 2: Create test app
print("\nTest 2: App Creation")
try:
    app = create_app('test')
    app.config['TESTING'] = True
    print(f"  [OK] App created in test mode")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

# Test 3: Access index page
print("\nTest 3: Index Page (GET /konferans/)")
with app.app_context():
    try:
        client = app.test_client()
        response = client.get('/konferans/')
        if response.status_code == 200:
            print(f"  [OK] GET /konferans/ returns 200")
            if b'Konferans' in response.data:
                print(f"  [OK] Page contains 'Konferans'")
            else:
                print(f"  [WARN] Page doesn't contain 'Konferans'")
        else:
            print(f"  [FAIL] GET /konferans/ returns {response.status_code}")
    except Exception as e:
        print(f"  [FAIL] {e}")

# Test 4: Billing constants
print("\nTest 4: Billing Configuration")
with app.app_context():
    try:
        from konferans.routes import FREE_MINUTES_DEFAULT, GKACH_PER_HOUR_DEFAULT, REMINDER_INTERVAL_MIN
        
        print(f"  Free minutes: {FREE_MINUTES_DEFAULT}")
        print(f"  Gkach/hour: {GKACH_PER_HOUR_DEFAULT}")
        print(f"  Reminder interval: {REMINDER_INTERVAL_MIN}")
        
        if (FREE_MINUTES_DEFAULT == 45 and 
            GKACH_PER_HOUR_DEFAULT == 250 and 
            REMINDER_INTERVAL_MIN == 10):
            print(f"  [OK] All billing constants correct")
        else:
            print(f"  [WARN] Some constants differ from expected")
    except Exception as e:
        print(f"  [FAIL] {e}")

# Test 5: Template
print("\nTest 5: Template Extends")
try:
    with open('templates/konferans/index.html') as f:
        first_line = f.readline().strip()
        if first_line == '{% extends "base.html" %}':
            print(f"  [OK] Template extends is correct")
        else:
            print(f"  [WARN] First line: {first_line[:50]}")
except Exception as e:
    print(f"  [FAIL] {e}")

# Test 6: Routes loaded
print("\nTest 6: Blueprint Registration")
with app.app_context():
    try:
        from konferans.routes import konferans_bp
        if konferans_bp:
            print(f"  [OK] Blueprint: {konferans_bp.name}")
            print(f"  [OK] URL prefix: {konferans_bp.url_prefix}")
    except Exception as e:
        print(f"  [FAIL] {e}")

# Test 7: Routes
print("\nTest 7: Route URLs")
with app.test_request_context('/'):
    try:
        from flask import url_for

        endpoints = [
            ('konferans.index', {}),
            ('konferans.create_room', {}),
            ('konferans.join_room_route', {}),
            ('konferans.upload_recording', {'room_id': 'TEST'}),
        ]

        for ep, kw in endpoints:
            try:
                url = url_for(ep, _external=False, **kw)
                print(f"  [OK] {ep} -> {url}")
            except Exception as e:
                print(f"  [FAIL] {ep}: {e}")
    except Exception as e:
        print(f"  [FAIL] {e}")

print("\n" + "=" * 60)
print("KONFERANS FEATURE TESTS COMPLETE")
print("=" * 60)
