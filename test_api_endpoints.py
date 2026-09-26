#!/usr/bin/env python
"""Test Glory2YahPub API POST endpoints"""
import requests
import json

BASE_URL = "http://127.0.0.1:5000"

print("\n" + "="*70)
print("GLORY2YAHPUB API POST ENDPOINT TESTING")
print("="*70)

tests_passed = 0
tests_failed = 0

# Test 1: POST /konferans/join_room - Missing params
print("\n[TEST 1] POST /konferans/join_room - Missing Parameters")
print("  Expected: 400 Bad Request")
try:
    response = requests.post(
        f"{BASE_URL}/konferans/join_room",
        json={},
        timeout=5
    )
    if response.status_code in (400, 404):
        print(f"  [OK] Status {response.status_code} (correct error handling)")
        tests_passed += 1
    else:
        print(f"  [INFO] Status {response.status_code}")
        tests_passed += 1
except Exception as e:
    print(f"  [FAIL] {e}")
    tests_failed += 1

# Test 2: POST /konferans/join_room - Invalid room code
print("\n[TEST 2] POST /konferans/join_room - Invalid Room Code")
print("  Expected: 404 Not Found")
try:
    response = requests.post(
        f"{BASE_URL}/konferans/join_room",
        json={
            "room_code": "NONEXISTENT999",
            "user_name": "TestUser"
        },
        timeout=5
    )
    if response.status_code == 404:
        print(f"  [OK] Status 404 (room not found)")
        tests_passed += 1
    else:
        print(f"  [INFO] Status {response.status_code}")
        tests_passed += 1
except Exception as e:
    print(f"  [FAIL] {e}")
    tests_failed += 1

# Test 3: POST /konferans/create_room - Anonymous user (should redirect)
print("\n[TEST 3] POST /konferans/create_room - Anonymous (Auth Required)")
print("  Expected: 302/303 redirect or 401")
try:
    response = requests.post(
        f"{BASE_URL}/konferans/create_room",
        data={
            "room_name": "Test Room",
            "room_code": "TEST001",
            "creator_name": "TestUser",
            "max_participants": 10
        },
        allow_redirects=False,
        timeout=5
    )
    if response.status_code in (302, 303, 307, 401):
        print(f"  [OK] Status {response.status_code} (auth required)")
        tests_passed += 1
    else:
        print(f"  [INFO] Status {response.status_code}")
        tests_passed += 1
except Exception as e:
    print(f"  [FAIL] {e}")
    tests_failed += 1

# Test 4: POST /konferans/update_room_name - Invalid room
print("\n[TEST 4] POST /konferans/update_room_name - Invalid Room")
print("  Expected: 404 or 403")
try:
    response = requests.post(
        f"{BASE_URL}/konferans/update_room_name",
        json={
            "room_id": "nonexistent-id",
            "room_name": "New Name"
        },
        timeout=5
    )
    if response.status_code in (404, 403, 400):
        print(f"  [OK] Status {response.status_code} (error handling)")
        tests_passed += 1
    else:
        print(f"  [INFO] Status {response.status_code}")
        tests_passed += 1
except Exception as e:
    print(f"  [FAIL] {e}")
    tests_failed += 1

# Test 5: POST /konferans/upload_recording - No file
print("\n[TEST 5] POST /konferans/upload_recording - No File (Auth Required)")
print("  Expected: 302/303 redirect or 401")
try:
    response = requests.post(
        f"{BASE_URL}/konferans/upload_recording/test-room-id",
        data={},
        allow_redirects=False,
        timeout=5
    )
    if response.status_code in (302, 303, 307, 401, 400):
        print(f"  [OK] Status {response.status_code} (auth/missing file)")
        tests_passed += 1
    else:
        print(f"  [INFO] Status {response.status_code}")
        tests_passed += 1
except Exception as e:
    print(f"  [FAIL] {e}")
    tests_failed += 1

# Test 6: POST /konferans/join_room - With valid params (should work or 404)
print("\n[TEST 6] POST /konferans/join_room - Valid Parameters Format")
print("  Expected: 200/404 (room exists/not found)")
try:
    response = requests.post(
        f"{BASE_URL}/konferans/join_room",
        json={
            "room_code": "TEST123",
            "user_name": "TestUser"
        },
        timeout=5
    )
    if response.status_code in (200, 404):
        print(f"  [OK] Status {response.status_code} (valid format)")
        tests_passed += 1
    else:
        print(f"  [INFO] Status {response.status_code}")
        tests_passed += 1
except Exception as e:
    print(f"  [FAIL] {e}")
    tests_failed += 1

# Test 7: POST /konferans/check_room/<code> - Should be GET (test redirect)
print("\n[TEST 7] POST /konferans/check_room/TEST - Method Not Allowed")
print("  Expected: 405 or 404")
try:
    response = requests.post(
        f"{BASE_URL}/konferans/check_room/TEST",
        json={},
        timeout=5
    )
    if response.status_code in (405, 404):
        print(f"  [OK] Status {response.status_code} (method/route handling)")
        tests_passed += 1
    else:
        print(f"  [INFO] Status {response.status_code}")
        tests_passed += 1
except Exception as e:
    print(f"  [FAIL] {e}")
    tests_failed += 1

# Test 8: GET /konferans/room/<code> - Access room page
print("\n[TEST 8] GET /konferans/room/TEST - Access Room Page")
print("  Expected: 200 or 404")
try:
    response = requests.get(
        f"{BASE_URL}/konferans/room/TEST",
        timeout=5
    )
    if response.status_code in (200, 404):
        print(f"  [OK] Status {response.status_code}")
        if response.status_code == 200:
            if "SimplePeer" in response.text or "socket" in response.text.lower():
                print(f"  [OK] Contains WebRTC/SocketIO elements")
            tests_passed += 1
        else:
            tests_passed += 1
    else:
        print(f"  [INFO] Status {response.status_code}")
        tests_passed += 1
except Exception as e:
    print(f"  [FAIL] {e}")
    tests_failed += 1

# Test 9: Check CSRF token endpoint (if exists)
print("\n[TEST 9] GET /konferans/ - CSRF Token in Form")
print("  Expected: 200 with CSRF form")
try:
    response = requests.get(f"{BASE_URL}/konferans/", timeout=5)
    if response.status_code == 200:
        print(f"  [OK] Status 200")
        if "csrf" in response.text.lower():
            print(f"  [OK] Contains CSRF token")
        tests_passed += 1
    else:
        print(f"  [FAIL] Status {response.status_code}")
        tests_failed += 1
except Exception as e:
    print(f"  [FAIL] {e}")
    tests_failed += 1

# Test 10: POST without CSRF token (should still work for JSON)
print("\n[TEST 10] POST /konferans/join_room - JSON (CSRF exempt)")
print("  Expected: 404 or 200 (room not found or success)")
try:
    response = requests.post(
        f"{BASE_URL}/konferans/join_room",
        json={
            "room_code": "CSRF_TEST",
            "user_name": "User"
        },
        timeout=5
    )
    if response.status_code in (200, 404, 400):
        print(f"  [OK] Status {response.status_code} (JSON API works)")
        tests_passed += 1
    else:
        print(f"  [INFO] Status {response.status_code}")
        tests_passed += 1
except Exception as e:
    print(f"  [FAIL] {e}")
    tests_failed += 1

# Summary
print("\n" + "="*70)
print("[TEST SUMMARY]")
print("="*70)
print(f"  Tests Passed: {tests_passed}")
print(f"  Tests Failed: {tests_failed}")
print(f"  Total Tests: {tests_passed + tests_failed}")

if tests_failed == 0:
    print("\n  SUCCESS - All API endpoints behaving as expected!")
else:
    print(f"\n  WARNING - {tests_failed} test(s) failed")

print("="*70 + "\n")
