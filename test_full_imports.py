import os
import sys
print("Testing imports...")

try:
    from app import create_app
    print("✓ Successfully imported create_app")
except Exception as e:
    print(f"✗ Failed to import create_app: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

try:
    app = create_app(os.environ.get('FLASK_ENV', 'development'))
    print("✓ Successfully created app instance")
    with app.app_context():
        print("✓ App context created")
        from app.models.user import User
        print("✓ Successfully imported User model")
        from app.models.ad import Ad
        print("✓ Successfully imported Ad model")
        from app.models.delivery import Delivery
        print("✓ Successfully imported Delivery model")
        print("\n✅ All imports test passed!")
except Exception as e:
    print(f"✗ Failed to create app: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
