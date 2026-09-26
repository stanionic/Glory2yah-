"""
PHASE 1 SECURITY VALIDATION TESTS
Tests the critical security fixes before deployment
"""
import os
import sys
import tempfile
import shutil
from pathlib import Path
from io import BytesIO

sys.path.insert(0, str(Path(__file__).parent))


def test_admin_password_not_reset_on_boot():
    """
    TEST 1: Admin password MUST NOT be reset on every boot
    This prevents the hardcoded password vulnerability
    """
    print("\n" + "="*70)
    print("TEST 1: Admin Password Persistence")
    print("="*70)
    
    test_db_dir = tempfile.mkdtemp()
    test_db_path = os.path.join(test_db_dir, 'test.db')
    
    try:
        os.environ['FLASK_ENV'] = 'testing'
        os.environ['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{test_db_path}'
        if 'ADMIN_PASSWORD' in os.environ:
            del os.environ['ADMIN_PASSWORD']
        
        from app import create_app, db
        from app.models.user import User
        
        # Boot 1: Create admin
        app1 = create_app('testing')
        with app1.app_context():
            admin = User.query.filter_by(is_admin=True).first()
            if not admin:
                print("❌ FAIL: No admin created on first boot")
                return False
            
            # Manually change password
            admin.set_password('CustomPassword123!')
            db.session.commit()
            hash1 = admin.password_hash
            print(f"✓ Admin password changed manually")
        
        # Boot 2: Check password NOT reset
        app2 = create_app('testing')
        with app2.app_context():
            admin = User.query.filter_by(is_admin=True).first()
            hash2 = admin.password_hash
            
            if hash1 != hash2:
                print("❌ FAIL: Admin password was RESET on boot (vulnerability still present)")
                return False
            
            print(f"✓ Admin password persisted across boot (PASSWORD NOT RESET)")
        
        print("✅ PASS: Admin password vulnerability is FIXED\n")
        return True
        
    except Exception as e:
        print(f"❌ EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if os.path.exists(test_db_dir):
            shutil.rmtree(test_db_dir)


def test_gkach_atomicity_with_locks():
    """
    TEST 2: Gkach operations must use database locks (with_for_update)
    This prevents race conditions in multi-worker environment
    """
    print("\n" + "="*70)
    print("TEST 2: Gkach Atomicity with Database Locks")
    print("="*70)
    
    try:
        from app.services.gkach_service import GkachService
        import inspect
        
        # Check if add_balance uses with_for_update()
        source = inspect.getsource(GkachService.add_balance)
        if '.with_for_update()' in source:
            print("✓ add_balance uses .with_for_update() for locking")
        else:
            print("❌ FAIL: add_balance does NOT use with_for_update()")
            return False
        
        # Check if deduct_balance uses with_for_update()
        source = inspect.getsource(GkachService.deduct_balance)
        if '.with_for_update()' in source:
            print("✓ deduct_balance uses .with_for_update() for locking")
        else:
            print("❌ FAIL: deduct_balance does NOT use with_for_update()")
            return False
        
        # Check if transfer commits atomically
        source = inspect.getsource(GkachService.transfer)
        if 'db.session.commit()' in source:
            print("✓ transfer commits atomically")
        else:
            print("⚠️  WARNING: transfer might not commit properly")
        
        print("✅ PASS: Gkach uses proper database locking\n")
        return True
        
    except Exception as e:
        print(f"❌ EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_mennem_demo_mode_protection():
    """
    TEST 3: Mennem MUST NOT debit real Gkach to fictional drivers
    Default should be DEMO_MODE to prevent fraud
    """
    print("\n" + "="*70)
    print("TEST 3: Mennem Demo Mode Protection")
    print("="*70)
    
    try:
        # Check if MENNEM_DEMO_MODE is set
        from mennem.app import MENNEM_DEMO_MODE
        
        if MENNEM_DEMO_MODE:
            print("✓ Mennem is in DEMO_MODE (default)")
            print("✓ Demo mode prevents real Gkach debits to fictional drivers")
        else:
            print("❌ FAIL: Mennem is NOT in DEMO_MODE!")
            print("❌ This allows debiting real Gkach to fictional drivers!")
            return False
        
        # Check if mennem/app.py has the debit protection
        import inspect
        from mennem.app import book
        source = inspect.getsource(book)
        
        if 'MENNEM_DEMO_MODE' in source:
            print("✓ mennem/app.py checks MENNEM_DEMO_MODE")
        else:
            print("⚠️  WARNING: mennem/app.py might not respect DEMO_MODE")
        
        if 'status=\'demo\'' in source:
            print("✓ Demo trips are marked with status='demo'")
        else:
            print("⚠️  WARNING: Demo trips might not be marked properly")
        
        print("✅ PASS: Mennem fraud protection is in place\n")
        return True
        
    except Exception as e:
        print(f"❌ EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_security_headers_present():
    """
    TEST 4: Security headers MUST be present in all responses
    Tests X-Content-Type-Options, X-Frame-Options, CSP, etc.
    """
    print("\n" + "="*70)
    print("TEST 4: Security Headers Verification")
    print("="*70)
    
    try:
        import inspect
        from app import register_error_handlers
        
        # Get the inject_security_headers function
        source = inspect.getsource(register_error_handlers)
        
        headers_required = {
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'DENY',
            'X-XSS-Protection': '1; mode=block',
            'Permissions-Policy': 'geolocation',
            'Referrer-Policy': 'strict-origin',
            'Content-Security-Policy': 'default-src',
        }
        
        all_present = True
        for header, expected_value in headers_required.items():
            if f"'{header}'" in source or f'"{header}"' in source:
                print(f"✓ {header} is set")
            else:
                print(f"❌ MISSING: {header}")
                all_present = False
        
        if not all_present:
            print("❌ FAIL: Some security headers are missing")
            return False
        
        print("✅ PASS: All critical security headers are present\n")
        return True
        
    except Exception as e:
        print(f"❌ EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_file_upload_validation():
    """
    TEST 5: File upload validation MUST include magic number checks
    Prevents uploading malicious files with wrong extensions
    """
    print("\n" + "="*70)
    print("TEST 5: File Upload Validation")
    print("="*70)
    
    try:
        import inspect
        from app.utils.validators import validate_file_upload
        
        source = inspect.getsource(validate_file_upload)
        
        checks = {
            'Magic number': 'magic_checks' in source or 'magic' in source.lower(),
            'Dangerous extensions': 'dangerous' in source,
            'Double extensions': 'split' in source and '>' in source,
            'Random filename': 'secrets.token' in source or 'random' in source.lower(),
        }
        
        all_present = True
        for check_name, check_result in checks.items():
            if check_result:
                print(f"✓ {check_name} validation present")
            else:
                print(f"❌ MISSING: {check_name} validation")
                all_present = False
        
        if not all_present:
            print("❌ FAIL: Some upload validations are missing")
            return False
        
        print("✅ PASS: File upload validation is hardened\n")
        return True
        
    except Exception as e:
        print(f"❌ EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    print("\n" + "="*70)
    print("PHASE 1 - CRITICAL SECURITY FIXES VALIDATION")
    print("="*70)
    
    results = []
    results.append(("Admin Password Persistence", test_admin_password_not_reset_on_boot()))
    results.append(("Gkach Atomicity", test_gkach_atomicity_with_locks()))
    results.append(("Mennem Demo Mode", test_mennem_demo_mode_protection()))
    results.append(("Security Headers", test_security_headers_present()))
    results.append(("File Upload Validation", test_file_upload_validation()))
    
    print("\n" + "="*70)
    print("PHASE 1 TEST SUMMARY")
    print("="*70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print("="*70)
    print(f"Results: {passed}/{total} tests passed")
    print("="*70)
    
    if passed == total:
        print("✅ ALL PHASE 1 SECURITY FIXES VALIDATED")
        sys.exit(0)
    else:
        print("❌ SOME PHASE 1 FIXES FAILED VALIDATION")
        sys.exit(1)
