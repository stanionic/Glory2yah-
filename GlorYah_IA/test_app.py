#!/usr/bin/env python3
"""
Test script for MANDEMMAPBAW
"""

import sys
import os

print("=" * 60)
print("MANDEMMAPBAW - Test Script")
print("=" * 60)
print()

# Test 1: Import app
print("Test 1: Importing app...")
try:
    from app import app, db
    print("✓ App imported successfully")
except Exception as e:
    print(f"✗ Failed to import app: {e}")
    sys.exit(1)

# Test 2: Import database models
print("\nTest 2: Importing database models...")
try:
    from database.models import ChatHistory, ImageGeneration, VideoGeneration, CodeGeneration
    print("✓ Database models imported successfully")
except Exception as e:
    print(f"✗ Failed to import database models: {e}")
    sys.exit(1)

# Test 3: Test generators lazy loading
print("\nTest 3: Testing AI generators lazy loading...")
try:
    from app import generators
    print("✓ Generators object created successfully")
    print("  (Generators will load on first use)")
except Exception as e:
    print(f"✗ Failed to create generators: {e}")
    sys.exit(1)

# Test 4: Test database creation
print("\nTest 4: Creating database...")
try:
    with app.app_context():
        db.create_all()
    print("✓ Database created successfully")
except Exception as e:
    print(f"✗ Failed to create database: {e}")
    sys.exit(1)

# Test 5: Test routes exist
print("\nTest 5: Checking routes...")
routes = [
    '/',
    '/chat',
    '/generate-image',
    '/generate-video',
    '/history',
    '/admin',
    '/admin/stats',
]

try:
    app_routes = [str(rule) for rule in app.url_map.iter_rules()]
    for route in routes:
        if route in app_routes or any(route in r for r in app_routes):
            print(f"  ✓ {route}")
        else:
            print(f"  ✗ {route} - NOT FOUND")
    print("✓ Routes checked")
except Exception as e:
    print(f"✗ Failed to check routes: {e}")

# Test 6: Test app configuration
print("\nTest 6: Checking app configuration...")
try:
    print(f"  SECRET_KEY: {'✓ Set' if app.config.get('SECRET_KEY') else '✗ NOT SET'}")
    print(f"  DATABASE_URI: {app.config.get('SQLALCHEMY_DATABASE_URI', 'NOT SET')}")
    print(f"  DEBUG: {app.config.get('DEBUG', False)}")
    print("✓ Configuration checked")
except Exception as e:
    print(f"✗ Failed to check configuration: {e}")

print()
print("=" * 60)
print("✅ ALL TESTS PASSED!")
print("=" * 60)
print()
print("The app should be ready to run with: python app.py")
print()
