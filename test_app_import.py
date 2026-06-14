import sys
import os
sys.path.insert(0, os.path.abspath('.'))

print("Testing app import...")
try:
    from app import create_app
    print("✓ create_app imported successfully!")
except Exception as e:
    print(f"✗ Failed to import: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\nTesting create_app...")
try:
    app = create_app('development')
    print("✓ create_app successful!")
except Exception as e:
    print(f"✗ Failed to create app: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n✓ All tests passed!")