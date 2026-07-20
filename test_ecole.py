"""Test script to debug ecole_biblique module"""
import sys
import os

# Add the project root to path so 'models' can be found
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'app'))

print("=" * 60)
print("ECOLE_BIBLIQUE DEBUG REPORT")
print("=" * 60)

# Fix: The line 'from models import db' in ecole_biblique/app.py
# needs the app/ directory in sys.path OR it needs 'from app import db'
print("\n[1] Import path for ecole_biblique")
print(f"    sys.path includes app/ dir: {os.path.join(project_root, 'app') in sys.path}")

print("\n[2] Testing ecole_biblique module import")
try:
    # We need to simulate how Flask imports it - with app context
    from app import db
    print("    OK - db imported from app")
except Exception as e:
    print(f"    ERROR importing app.db: {type(e).__name__}: {e}")

print("\n[3] Testing blueprint registration path")
print("    In app/__init__.py line 256:")
print("        from ecole_biblique.app import ecole_biblique_bp")
print("    This tries to import ecole_biblique which does:")
print("        from models import db")
print("    But 'models' is actually in 'app/models/__init__.py'")
print("    FIX: Change 'from models import db' to 'from app import db'")

print("\n[4] Testing template paths")
print("    render_template('ecole_biblique/login.html')")
print("    expects template at: templates/ecole_biblique/login.html")
main_templates = os.path.join(project_root, 'templates', 'ecole_biblique')
if os.path.exists(main_templates):
    print(f"    OK - templates/ecole_biblique/ exists")
else:
    print(f"    MISSING - templates/ecole_biblique/ doesn't exist")
    print(f"    Templates are in ecole_biblique/templates/ instead")
    
print("\n[5] Checking missing models (EcoleUser, Course, Grade, EcoleStudent)")
try:
    from app import app as flask_app
    with flask_app.app_context():
        import app.models as models
        for name in ['EcoleUser', 'EcoleStudent', 'Course', 'Grade']:
            if hasattr(models, name):
                print(f"    OK - {name} found in app.models")
            else:
                print(f"    MISSING - {name} not in app.models")
except Exception as e:
    print(f"    ERROR checking models: {type(e).__name__}: {e}")

print("\n[6] template_folder in ecole_biblique blueprint")
print("    Current: No template_folder set -> uses app's template_folder")
print("    Which is: '../templates' -> resolves to project_root/templates")
print("    FIX: Add template_folder='../ecole_biblique/templates' to Blueprint()")

print("\n" + "=" * 60)
print("SUMMARY OF BUGS FOUND:")
print("=" * 60)
print("1. ecole_biblique/app.py line 4: 'from models import db'")
print("   FIX: Change to 'from app import db'")
print("2. ecole_biblique/app.py line 12,21,35,50,73,80,90,99,112: Imports like")
print("   'from app import EcoleUser as User' but EcoleUser doesn't exist")
print("   FIX: Use 'from app.models.user import User' instead")
print("3. ecole_biblique doesn't set template_folder")
print("   FIX: Add template_folder='../ecole_biblique/templates' to Blueprint()")
print("4. script.js line 3: fetch('/api/grades/${courseId}')")
print("   FIX: Change to fetch('/ecole_biblique/api/grades/${courseId}')")