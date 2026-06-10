#!/usr/bin/env python3
"""
MANDEMMAPBAW - Smart Startup Script
Automatically detects available dependencies and starts in appropriate mode
"""

import sys
import os

print("=" * 70)
print("MANDEMMAPBAW - Intelligent Startup")
print("=" * 70)
print()

# Check Python version
if sys.version_info < (3, 8):
    print("❌ Error: Python 3.8+ required")
    print(f"   Current version: {sys.version}")
    sys.exit(1)

print(f"✓ Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")

# Check dependencies
print("\nChecking dependencies...")

required_basic = ['flask', 'flask_sqlalchemy', 'flask_cors']
optional_ai = ['torch', 'transformers', 'diffusers']
video_deps = ['PIL', 'cv2', 'numpy']

missing_basic = []
missing_ai = []
missing_video = []

for module in required_basic:
    try:
        __import__(module)
        print(f"  ✓ {module}")
    except ImportError:
        missing_basic.append(module)
        print(f"  ✗ {module} - MISSING")

if missing_basic:
    print("\n❌ Critical dependencies missing!")
    print("   Install with: pip install -r requirements-basic.txt")
    sys.exit(1)

# Check optional AI deps
ai_available = True
for module in optional_ai:
    try:
        __import__(module)
        print(f"  ✓ {module} (AI)")
    except ImportError:
        ai_available = False
        missing_ai.append(module)
        print(f"  ⚠ {module} (AI) - not available")

# Check video deps
video_available = True
for module in video_deps:
    try:
        __import__(module)
        print(f"  ✓ {module} (video)")
    except ImportError:
        video_available = False
        missing_video.append(module)
        print(f"  ⚠ {module} (video) - not available")

print("\n" + "-" * 70)

# Determine startup mode
if ai_available and video_available:
    mode = "FULL"
    print("🚀 Starting in FULL MODE")
    print("   All features available: Text, Image, Video, Code generation")
elif video_available:
    mode = "VIDEO_ONLY"
    print("🎬 Starting in VIDEO MODE")
    print("   Available: Video generation, basic responses")
    print("   Not available: AI text/image/code generation")
else:
    mode = "FALLBACK"
    print("💡 Starting in FALLBACK MODE")
    print("   Available: Basic API, fallback responses")
    print("   Not available: AI features, video generation")

print("-" * 70)

# Import and start app
print("\nLoading application...")

try:
    from app import app, init_db
    print("✓ App loaded successfully")
except Exception as e:
    print(f"❌ Error loading app: {e}")
    sys.exit(1)

# Initialize database
print("Initializing database...")
try:
    init_db()
    print("✓ Database ready")
except Exception as e:
    print(f"❌ Database error: {e}")
    sys.exit(1)

# Start server
print("\n" + "=" * 70)
print("🌐 Starting MANDEMMAPBAW Server")
print("=" * 70)

host = os.environ.get('FLASK_HOST', '0.0.0.0')
port = int(os.environ.get('FLASK_PORT', 5000))
debug = os.environ.get('FLASK_ENV') == 'development'

print(f"\n   URL: http://{host}:{port}")
print(f"   Mode: {mode}")
print(f"   Debug: {debug}")
print()

if missing_ai:
    print("📝 To enable AI features, install:")
    print("   pip install -r requirements.txt")
    print()

if missing_video and not missing_ai:
    print("📝 To enable video generation, install:")
    print("   pip install Pillow numpy opencv-python")
    print()

print("Press Ctrl+C to stop")
print()

try:
    app.run(host=host, port=port, debug=debug)
except KeyboardInterrupt:
    print("\n\n👋 Server stopped by user")
except Exception as e:
    print(f"\n\n❌ Server error: {e}")
    sys.exit(1)
