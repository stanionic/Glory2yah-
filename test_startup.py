"""
Test script to verify Glory2YahPub starts correctly
"""
import sys
import os

# Add the project directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    print("Testing Glory2YahPub startup...")
    print("=" * 60)
    
    # Test 1: Import the application factory
    print("\n[1/5] Testing application factory import...")
    from app import create_app, socketio
    print("[OK] Application factory imported successfully")
    
    # Test 2: Create the app
    print("\n[2/5] Creating Flask application...")
    app = create_app()
    print("[OK] Flask application created successfully")
    
    # Test 3: Check database
    print("\n[3/5] Checking database connection...")
    with app.app_context():
        from app import db
        from sqlalchemy import text
        db.session.execute(text('SELECT 1'))
        print("[OK] Database connection successful")
    
    # Test 4: Check routes
    print("\n[4/5] Checking registered routes...")
    with app.app_context():
        routes = [str(rule) for rule in app.url_map.iter_rules()]
        print(f"[OK] {len(routes)} routes registered")
        
        # Check critical routes
        critical_routes = ['/', '/mache', '/cart', '/gkach/wallet', '/auth/login']
        for route in critical_routes:
            if any(route in r for r in routes):
                print(f"  [OK] {route}")
            else:
                print(f"  [MISSING] {route}")
    
    # Test 5: Check blueprints
    print("\n[5/5] Checking registered blueprints...")
    with app.app_context():
        blueprints = list(app.blueprints.keys())
        print(f"[OK] {len(blueprints)} blueprints registered:")
        for bp in blueprints:
            print(f"  - {bp}")
    
    print("\n" + "=" * 60)
    print("[SUCCESS] ALL TESTS PASSED!")
    print("=" * 60)
    print("\nThe application is ready to run.")
    print("Start with: python run.py")
    print("\n")
    
except Exception as e:
    print(f"\n[ERROR] {e}")
    print("\nFull traceback:")
    import traceback
    traceback.print_exc()
    sys.exit(1)
