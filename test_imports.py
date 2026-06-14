#!/usr/bin/env python3
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
    app = create_app('development')
    print("✓ Successfully created app")
except Exception as e:
    print(f"✗ Failed to create app: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("✅ All tests passed!")