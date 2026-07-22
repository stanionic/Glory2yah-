"""
Konferans Debug Script
Tests all routes, URL generation, template rendering
"""
import sys
import os
import traceback

print("=" * 60)
print("KONFERANS DEBUG DIAGNOSTIC")
print("=" * 60)

# 1. Check import
print("\n[1] Testing imports...")
try:
    from konferans.routes import konferans_bp, register_socketio_handlers
    print(f"  ✅ konferans_bp: {konferans_bp.name}")
    print(f"  ✅ register_socketio_handlers: {register_socketio_handlers}")
except Exception as e:
    print(f"  ❌ Import error: {e}")
    traceback.print_exc()

# 2. Test the URL prefix conflict
print("\n[2] Checking URL prefix conflict...")
print(f"  Blueprint url_prefix: {konferans_bp.url_prefix}")
print(f"  In app/__init__.py, it's registered with url_prefix='/konferans'")
print(f"  ⚠️  DOUBLE PREFIX! Actual route would be: /konferans/konferans/")

# 3. Create app & test routes
print("\n[3] Creating app and testing routes...")
try:
    from app import create_app
    app = create_app('development')
    
    with app.test_request_context():
        from flask import url_for, render_template_string
        
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
                print(f"    ✅ {ep} -> {url}")
            except Exception as e:
                print(f"    ❌ {ep} -> {e}")
        
        # Test old-style endpoints used in room.html template
        old_endpoints = ['index', 'achte', 'achte_gkach', 'submit_ad', 'admin']
        print("\n  Old Endpoints (used in room.html nav):")
        for ep in old_endpoints:
            try:
                url = url_for(ep)
                print(f"    ✅ {ep} -> {url}")
            except Exception as e:
                print(f"    ❌ {ep} -> {e}")
        
        # Test template rendering
        print("\n  Template Rendering Tests:")
        
        # Test index template
        try:
            from flask import render_template
            rendered = render_template('konferans/index.html')
            # Check for error indicators
            if 'UndefinedError' in rendered or 'NoneType' in rendered:
                print(f"    ⚠️  index.html: Rendered but may have undefined variables")
            else:
                print(f"    ✅ index.html: Rendered successfully ({len(rendered)} chars)")
        except Exception as e:
            print(f"    ❌ index.html: {e}")
        
        # Simulate room rendering (needs room data)
        try:
            # Create a mock room for testing
            from app.models.konferans import KonferansRoom
            from app import db
            
            # Check if KonferansRoom table exists
            import sqlalchemy
            inspector = sqlalchemy.inspect(db.engine)
            tables = inspector.get_table_names()
            if 'konferans_rooms' in tables:
                print(f"    ✅ konferans_rooms table exists")
            else:
                print(f"    ⚠️  konferans_rooms table not found in: {tables}")
                
        except Exception as e:
            print(f"    ℹ️  DB check: {e}")

except Exception as e:
    print(f"  ❌ App creation error: {e}")
    traceback.print_exc()

# 4. Check template directory structure
print("\n[4] Checking template directory...")
import os
templates_dir = 'konferans/templates'
if os.path.exists(templates_dir):
    files = os.listdir(templates_dir)
    print(f"  ✅ Directory exists. Files: {files}")
else:
    print(f"  ❌ Directory not found!")

# 5. Check if static files referenced exist
print("\n[5] Checking static files...")
logo_path = 'static/images/logo.svg'
if os.path.exists(logo_path):
    print(f"  ✅ logo.svg exists")
else:
    print(f"  ⚠️  logo.svg not found at {logo_path}")

# 6. Check SocketIO configuration
print("\n[6] SocketIO Configuration...")
try:
    from app import socketio
    print(f"  ✅ socketio initialized: {socketio}")
    print(f"  ℹ️  SocketIO async mode: {socketio.async_mode}")
except Exception as e:
    print(f"  ❌ SocketIO error: {e}")

# 7. Summary
print("\n" + "=" * 60)
print("SUMMARY OF ISSUES FOUND")
print("=" * 60)
print("""
Likely Issues:
1. 🔴 DOUBLE URL PREFIX: Blueprint has url_prefix='/konferans' AND 
   app.register_blueprint(konferans_bp, url_prefix='/konferans')
   → Actual URLs will be /konferans/konferans/...

2. 🔴 OLD ENDPOINT NAMES: room.html uses url_for('index'), url_for('achte'), 
   url_for('submit_ad'), url_for('admin') which may fail due to modular architecture

3. ⚠️  STATIC FILES: logo.svg may not exist at expected path

4. ⚠️  TEMPLATE EXTENDS: index.html extends "base.html" but room.html is standalone

5. ⚠️  SOCKETIO: Must register handlers correctly with the app's socketio instance
""")
