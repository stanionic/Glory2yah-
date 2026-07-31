"""
Konferans Debug Script (Fixed for Windows cp1252)
Tests all routes, URL generation, template rendering
"""
import sys
import os
import traceback

print("=" * 60)
print("KONFERANS DEBUG DIAGNOSTIC")
print("=" * 60)

SET_PYTHONIOENCODING = 'utf-8'  # Force UTF-8

# 1. Check import
print("\n[1] Testing imports...")
try:
    from konferans.routes import konferans_bp, register_socketio_handlers
    print(f"  [OK] konferans_bp: {konferans_bp.name}")
    print(f"  [OK] register_socketio_handlers: {register_socketio_handlers}")
except Exception as e:
    print(f"  [FAIL] Import error: {e}")
    traceback.print_exc()

# 2. Test the URL prefix
print("\n[2] Checking URL prefix...")
try:
    print(f"  Blueprint url_prefix: {konferans_bp.url_prefix}")
    print(f"  In app/__init__.py, registered WITHOUT extra url_prefix")
    print(f"  Actual route: /konferans/...")
except Exception as e:
    print(f"  [FAIL] Prefix check error: {e}")

# 3. Create app & test routes
print("\n[3] Creating app and testing routes...")
try:
    from app import create_app
    app = create_app('development')
    
    with app.test_request_context():
        from flask import url_for
        
        # Test URL generation for konferans
        print("\n  URL Generation Tests:")
        endpoints_to_test = [
            'konferans.index',
            'konferans.room',
            'konferans.create_room',
            'konferans.join_room_route',
            'konferans.check_room',
            'konferans.upload_recording',
        ]
        
        for ep in endpoints_to_test:
            try:
                url = url_for(ep)
                print(f"    [OK] {ep} -> {url}")
            except Exception as e:
                print(f"    [FAIL] {ep} -> {e}")
        
        # Test old-style endpoints used in room.html template
        old_endpoints = ['index', 'achte', 'achte_gkach', 'submit_ad', 'admin']
        print("\n  Old Endpoints (used in room.html nav):")
        for ep in old_endpoints:
            try:
                url = url_for(ep)
                print(f"    [OK] {ep} -> {url}")
            except Exception as e:
                print(f"    [FAIL] {ep} -> {e}")
        
        # Test template rendering
        print("\n  Template Rendering Tests:")
        
        # Test index template
        try:
            from flask import render_template
            rendered = render_template('konferans/index.html')
            print(f"    [OK] index.html: Rendered successfully ({len(rendered)} chars)")
        except Exception as e:
            print(f"    [FAIL] index.html: {e}")
        
        # Test room template
        try:
            from app.models.konferans import KonferansRoom
            room = KonferansRoom(
                room_id='test-room-id',
                room_code='TEST01',
                room_name='Test Room',
                creator_name='Test User',
            )
            rendered = render_template('konferans/room.html', room=room, user_name='Test User', is_owner=True)
            print(f"    [OK] room.html: Rendered successfully ({len(rendered)} chars)")
        except Exception as e:
            print(f"    [FAIL] room.html: {e}")
        
        # Check if KonferansRoom table exists
        try:
            from app import db
            import sqlalchemy
            inspector = sqlalchemy.inspect(db.engine)
            tables = inspector.get_table_names()
            if 'konferans_rooms' in tables:
                print(f"    [OK] konferans_rooms table exists")
            else:
                print(f"    [WARN] konferans_rooms table not found in: {tables}")
        except Exception as e:
            print(f"    [INFO] DB check: {e}")

except Exception as e:
    print(f"  [FAIL] App creation error: {e}")
    traceback.print_exc()

# 4. Check template directory structure
print("\n[4] Checking template directory...")
templates_dir = 'konferans/templates'
if os.path.exists(templates_dir):
    files = os.listdir(templates_dir)
    print(f"  [OK] konferans/templates/ exists. Files: {files}")
else:
    print(f"  [FAIL] konferans/templates/ not found!")

# Check templates/konferans directory
templates_dir2 = 'templates/konferans'
if os.path.exists(templates_dir2):
    files = os.listdir(templates_dir2)
    print(f"  [OK] templates/konferans/ exists. Files: {files}")
else:
    print(f"  [FAIL] templates/konferans/ not found!")

# 5. Check if static files referenced exist
print("\n[5] Checking static files...")
logo_path = 'static/images/logo.svg'
if os.path.exists(logo_path):
    print(f"  [OK] logo.svg exists")
else:
    print(f"  [WARN] logo.svg not found at {logo_path}")

# 6. Check SocketIO configuration
print("\n[6] SocketIO Configuration...")
try:
    from app import socketio
    print(f"  [OK] socketio initialized: {socketio}")
    print(f"  [INFO] SocketIO async mode: {socketio.async_mode}")
except Exception as e:
    print(f"  [FAIL] SocketIO error: {e}")

# 7. Summary
print("\n" + "=" * 60)
print("DEBUG COMPLETE")
print("=" * 60)