"""
Glory2YahPub - Diagnostic and Auto-Fix Script
This script checks for common issues and attempts to fix them automatically
"""
import sys
import os

print("=" * 60)
print("GLORY2YAHPUB - DIAGNOSTIC TOOL")
print("=" * 60)
print()

# Change to script directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

issues_found = []
fixes_applied = []

# Check 1: Python version
print("[1/8] Checking Python version...")
if sys.version_info < (3, 8):
    issues_found.append("Python version too old (need 3.8+)")
    print("  [ERROR] Python 3.8+ required")
else:
    print("  [OK] Python", sys.version.split()[0])

# Check 2: Required directories
print("\n[2/8] Checking directories...")
required_dirs = ['app', 'templates', 'static', 'instance', 'logs']
for dir_name in required_dirs:
    if not os.path.exists(dir_name):
        print(f"  [FIX] Creating {dir_name}/")
        os.makedirs(dir_name, exist_ok=True)
        fixes_applied.append(f"Created {dir_name}/ directory")
    else:
        print(f"  [OK] {dir_name}/")

# Check 3: Database directory
print("\n[3/8] Checking database...")
if not os.path.exists('instance/glory2yahpub.db'):
    print("  [INFO] Database will be created on first run")
else:
    size = os.path.getsize('instance/glory2yahpub.db')
    print(f"  [OK] Database exists ({size} bytes)")

# Check 4: Required files
print("\n[4/8] Checking required files...")
required_files = [
    'run.py',
    'app/__init__.py',
    'app/config.py',
    'requirements.txt'
]
for file_path in required_files:
    if not os.path.exists(file_path):
        issues_found.append(f"Missing file: {file_path}")
        print(f"  [ERROR] Missing {file_path}")
    else:
        print(f"  [OK] {file_path}")

# Check 5: Import test
print("\n[5/8] Testing imports...")
try:
    from app import create_app, socketio
    print("  [OK] Application factory imports")
except ImportError as e:
    issues_found.append(f"Import error: {e}")
    print(f"  [ERROR] {e}")
except Exception as e:
    issues_found.append(f"Import error: {e}")
    print(f"  [ERROR] {e}")

# Check 6: Create app test
print("\n[6/8] Testing app creation...")
try:
    from app import create_app
    app = create_app()
    print("  [OK] App created successfully")
except Exception as e:
    issues_found.append(f"App creation error: {e}")
    print(f"  [ERROR] {e}")

# Check 7: Database test
print("\n[7/8] Testing database...")
try:
    from app import create_app, db
    from sqlalchemy import text
    app = create_app()
    with app.app_context():
        db.session.execute(text('SELECT 1'))
        print("  [OK] Database connection works")
except Exception as e:
    issues_found.append(f"Database error: {e}")
    print(f"  [ERROR] {e}")

# Check 8: Port availability
print("\n[8/8] Checking port 8080...")
import socket
try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('localhost', 8080))
    sock.close()
    if result == 0:
        print("  [WARNING] Port 8080 is already in use")
        print("  [INFO] Stop other apps or use a different port")
    else:
        print("  [OK] Port 8080 is available")
except Exception as e:
    print(f"  [WARNING] Could not check port: {e}")

# Summary
print("\n" + "=" * 60)
if issues_found:
    print("ISSUES FOUND:")
    for issue in issues_found:
        print(f"  - {issue}")
    print("\nPlease fix these issues before running the app.")
    print("=" * 60)
    sys.exit(1)
else:
    print("ALL CHECKS PASSED!")
    if fixes_applied:
        print("\nAuto-fixes applied:")
        for fix in fixes_applied:
            print(f"  - {fix}")
    print("\nThe application is ready to run!")
    print("Start with: python run.py")
    print("Or double-click: RUN_APP.bat")
    print("=" * 60)
    sys.exit(0)
