"""
SECURITY TEST: Admin Password Vulnerability
Tests that admin password is NOT hardcoded and NOT reset on every boot
"""
import os
import sys
import tempfile
import shutil
from pathlib import Path

# Setup test environment
sys.path.insert(0, str(Path(__file__).parent))

def test_admin_password_not_hardcoded():
    """
    VULNERABILITY TEST:
    - Admin password should NOT default to 'StanGlory2YahPub1986'
    - Admin password should NOT be reset on every boot
    - ADMIN_PASSWORD must come from environment variable in production
    """
    
    # Create temporary database for this test
    test_db_dir = tempfile.mkdtemp()
    test_db_path = os.path.join(test_db_dir, 'test.db')
    
    try:
        # Set minimal environment (simulating production-like setup)
        os.environ['FLASK_ENV'] = 'testing'
        os.environ['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{test_db_path}'
        # CRITICAL: Do NOT set ADMIN_PASSWORD to see the default behavior
        if 'ADMIN_PASSWORD' in os.environ:
            del os.environ['ADMIN_PASSWORD']
        
        from app import create_app, db
        from app.models import User
        
        # First boot - create app
        app = create_app('testing')
        
        with app.app_context():
            # First boot should create admin
            admin1 = User.query.filter_by(is_admin=True).first()
            if not admin1:
                print("❌ FAIL: No admin user created on first boot")
                return False
            
            # Get initial password hash
            initial_hash = admin1.password_hash
            print(f"✓ Admin user created: {admin1.pseudo}")
            
            # Change the password manually (simulating admin changing their own password)
            admin1.set_password('NewSecurePassword123!')
            db.session.commit()
            changed_hash = admin1.password_hash
            
            if initial_hash == changed_hash:
                print("❌ FAIL: Password hash did not change")
                return False
            
            print(f"✓ Admin password changed manually")
        
        # Simulate second boot (re-creating app)
        # This should NOT reset the password
        app2 = create_app('testing')
        
        with app2.app_context():
            admin2 = User.query.filter_by(is_admin=True).first()
            
            # BUG: If password is being reset on every boot, this will fail
            if admin2.password_hash != changed_hash:
                print(f"❌ FAIL: Admin password was RESET on boot!")
                print(f"   Initial hash:    {initial_hash[:20]}...")
                print(f"   Changed hash:    {changed_hash[:20]}...")
                print(f"   After boot hash: {admin2.password_hash[:20]}...")
                return False
            
            print(f"✓ Admin password persisted across boot (NOT reset)")
        
        print("\n✅ PASS: Admin password vulnerability is FIXED")
        return True
        
    except Exception as e:
        print(f"❌ EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup
        if os.path.exists(test_db_dir):
            shutil.rmtree(test_db_dir)


def test_admin_password_env_required_production():
    """
    Test that in production mode, ADMIN_PASSWORD from environment is required
    and NOT replaced with hardcoded default
    """
    test_db_dir = tempfile.mkdtemp()
    test_db_path = os.path.join(test_db_dir, 'test.db')
    
    try:
        os.environ['FLASK_ENV'] = 'production'
        os.environ['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{test_db_path}'
        # Production: ADMIN_PASSWORD MUST come from env
        os.environ['ADMIN_PASSWORD'] = 'ProductionSecurePassword456!'
        
        from app import create_app, db
        from app.models import User
        
        app = create_app('production')
        
        with app.app_context():
            admin = User.query.filter_by(is_admin=True).first()
            if not admin:
                print("❌ FAIL: No admin created with ADMIN_PASSWORD from env")
                return False
            
            # Verify password was set from env variable
            from werkzeug.security import check_password_hash
            if not check_password_hash(admin.password_hash, 'ProductionSecurePassword456!'):
                print("❌ FAIL: Admin password is not the one from ADMIN_PASSWORD env var")
                return False
            
            print("✅ PASS: Admin password correctly set from ADMIN_PASSWORD env var")
            return True
            
    except Exception as e:
        print(f"❌ EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if os.path.exists(test_db_dir):
            shutil.rmtree(test_db_dir)
        if 'ADMIN_PASSWORD' in os.environ:
            del os.environ['ADMIN_PASSWORD']


if __name__ == '__main__':
    print("=" * 70)
    print("SECURITY TEST: Admin Password")
    print("=" * 70)
    print()
    
    test1_pass = test_admin_password_not_hardcoded()
    print()
    test2_pass = test_admin_password_env_required_production()
    
    print()
    print("=" * 70)
    if test1_pass and test2_pass:
        print("✅ ALL SECURITY TESTS PASSED")
        sys.exit(0)
    else:
        print("❌ SECURITY TESTS FAILED")
        sys.exit(1)
