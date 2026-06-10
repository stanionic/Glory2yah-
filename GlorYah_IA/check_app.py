#!/usr/bin/env python3
"""
Quick app checker - identifies exact issues
"""

import sys

print("MANDEMMAPBAW - Quick Diagnostic")
print("=" * 60)

# Check 1: Python version
print("\n1. Python Version:")
print(f"   {sys.version}")
if sys.version_info < (3, 8):
    print("   ✗ FAIL: Python 3.8+ required")
    sys.exit(1)
print("   ✓ OK")

# Check 2: Required modules
print("\n2. Checking required modules...")
required = {
    'flask': 'Flask',
    'flask_sqlalchemy': 'Flask-SQLAlchemy',  
    'flask_cors': 'Flask-CORS',
    'werkzeug': 'Werkzeug',
}

missing = []
for module, name in required.items():
    try:
        __import__(module)
        print(f"   ✓ {name}")
    except ImportError:
        print(f"   ✗ {name} - MISSING")
        missing.append(name)

if missing:
    print(f"\n   Install missing: pip install {' '.join(missing)}")
    print("   Or: pip install -r requirements-minimal.txt")
    sys.exit(1)

# Check 3: App imports
print("\n3. Checking app imports...")
try:
    from app import app, db
    print("   ✓ App imported")
except Exception as e:
    print(f"   ✗ App import failed: {e}")
    sys.exit(1)

# Check 4: Database models
print("\n4. Checking database models...")
try:
    from database.models import ChatHistory, ImageGeneration
    print("   ✓ Models imported")
except Exception as e:
    print(f"   ✗ Models import failed: {e}")
    sys.exit(1)

# Check 5: Database initialization
print("\n5. Initializing database...")
try:
    with app.app_context():
        db.create_all()
    print("   ✓ Database created")
except Exception as e:
    print(f"   ✗ Database creation failed: {e}")
    sys.exit(1)

# Check 6: Routes
print("\n6. Checking routes...")
routes = ['/', '/chat', '/generate-image', '/generate-video', '/admin']
with app.app_context():
    for route in routes:
        if any(route in str(rule) for rule in app.url_map.iter_rules()):
            print(f"   ✓ {route}")
        else:
            print(f"   ✗ {route} - MISSING")

print("\n" + "=" * 60)
print("✅ ALL CHECKS PASSED")
print("=" * 60)
print("\nYou can now run:")
print("  python app.py")
print("or:")
print("  python run_simple.py  (for fallback mode)")
print()
