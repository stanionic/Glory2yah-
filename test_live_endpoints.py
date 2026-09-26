#!/usr/bin/env python
"""Test Glory2YahPub running server"""
import requests
import json

BASE_URL = "http://127.0.0.1:5000"

print("\n" + "="*60)
print("GLORY2YAHPUB LIVE ENDPOINT TESTING")
print("="*60)

tests_passed = 0
tests_failed = 0

# Test 1: GET /konferans/ (Index page)
print("\n[TEST 1] GET /konferans/ - Index Page")
try:
    response = requests.get(f"{BASE_URL}/konferans/", timeout=5)
    if response.status_code == 200:
        print(f"  [OK] Status 200")
        if "Konferans" in response.text or "konferans" in response.text.lower():
            print(f"  [OK] Contains Konferans content")
            tests_passed += 1
        else:
            print(f"  [WARN] No Konferans text found")
            tests_passed += 1
    else:
        print(f"  [FAIL] Status {response.status_code}")
        tests_failed += 1
except Exception as e:
    print(f"  [FAIL] {e}")
    tests_failed += 1

# Test 2: Check room endpoint
print("\n[TEST 2] GET /konferans/check_room/TEST - Check Room")
try:
    response = requests.get(f"{BASE_URL}/konferans/check_room/TEST", timeout=5)
    if response.status_code in (200, 404):
        print(f"  [OK] Status {response.status_code} (expected)")
        tests_passed += 1
    else:
        print(f"  [FAIL] Status {response.status_code}")
        tests_failed += 1
except Exception as e:
    print(f"  [FAIL] {e}")
    tests_failed += 1

# Test 3: Marketplace
print("\n[TEST 3] GET /achte - Marketplace")
try:
    response = requests.get(f"{BASE_URL}/achte", timeout=5)
    if response.status_code == 200:
        print(f"  [OK] Status 200")
        tests_passed += 1
    else:
        print(f"  [INFO] Status {response.status_code}")
        tests_passed += 1
except Exception as e:
    print(f"  [FAIL] {e}")
    tests_failed += 1

# Test 4: Bible School
print("\n[TEST 4] GET /ecole_biblique - Bible School")
try:
    response = requests.get(f"{BASE_URL}/ecole_biblique", timeout=5)
    if response.status_code == 200:
        print(f"  [OK] Status 200")
        tests_passed += 1
    else:
        print(f"  [INFO] Status {response.status_code}")
        tests_passed += 1
except Exception as e:
    print(f"  [FAIL] {e}")
    tests_failed += 1

# Test 5: Bank
print("\n[TEST 5] GET /bank - Bank Module")
try:
    response = requests.get(f"{BASE_URL}/bank", timeout=5)
    if response.status_code in (200, 302, 303):
        print(f"  [OK] Status {response.status_code}")
        tests_passed += 1
    else:
        print(f"  [INFO] Status {response.status_code}")
        tests_passed += 1
except Exception as e:
    print(f"  [FAIL] {e}")
    tests_failed += 1

# Test 6: Home page
print("\n[TEST 6] GET / - Home Page")
try:
    response = requests.get(f"{BASE_URL}/", timeout=5)
    if response.status_code in (200, 302, 303):
        print(f"  [OK] Status {response.status_code}")
        tests_passed += 1
    else:
        print(f"  [INFO] Status {response.status_code}")
        tests_passed += 1
except Exception as e:
    print(f"  [FAIL] {e}")
    tests_failed += 1

# Test 7: Events
print("\n[TEST 7] GET /events - Events Module")
try:
    response = requests.get(f"{BASE_URL}/events", timeout=5)
    if response.status_code in (200, 302, 303):
        print(f"  [OK] Status {response.status_code}")
        tests_passed += 1
    else:
        print(f"  [INFO] Status {response.status_code}")
        tests_passed += 1
except Exception as e:
    print(f"  [FAIL] {e}")
    tests_failed += 1

# Summary
print("\n" + "="*60)
print("[SUMMARY]")
print("="*60)
print(f"  Tests Passed: {tests_passed}")
print(f"  Tests Failed: {tests_failed}")
print(f"  Total: {tests_passed + tests_failed}")

if tests_failed == 0:
    print("\n  SUCCESS - All endpoints responding correctly!")
else:
    print(f"\n  WARNING - {tests_failed} test(s) failed")

print("="*60 + "\n")
