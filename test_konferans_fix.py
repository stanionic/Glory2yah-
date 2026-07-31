"""Verify KONFERANS fixes"""
import sys
sys.path.insert(0, 'c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub - Copy')

# Test 1: Import db correctly
from app import db
print("✅ Test 1: 'from app import db' works")

# Test 2: Import konferans_bp
from konferans.routes import konferans_bp, register_socketio_handlers
print(f"✅ Test 2: konferans_bp imported, url_prefix='{konferans_bp.url_prefix}'")

# Test 3: Create app and verify routes
from app import create_app
app = create_app('development')
print("✅ Test 3: App created successfully")

with app.test_request_context():
    from flask import url_for
    
    # Test all konferans routes
    routes = {
        'konferans.index': '/',
        'konferans.create_room': '/create_room',
        'konferans.join_room_route': '/join_room',
        'konferans.check_room': '/check_room/TEST123',
        'konferans.room': '/room/TEST123',
        'konferans.upload_recording': '/upload_recording/test-id',
        'konferans.update_room_name': '/update_room_name',
        'konferans.download_recording': '/download_recording/test.webm',
    }
    
    for endpoint, expected_path in routes.items():
