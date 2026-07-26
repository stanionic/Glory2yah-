"""
Fix test user credentials and setup
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app, db
from app.models.user import User
from app.models.user_gkach import UserGkach

app = create_app()

with app.app_context():
    # Check existing users
    users = User.query.all()
    print(f"Total users: {len(users)}")
    for u in users:
        pw_ok = u.check_password('123456') if u.password_hash else False
        print(f"  ID={u.id}, pseudo={u.pseudo}, whatsapp={u.whatsapp}, has_password={bool(u.password_hash)}, pw_check_123456={pw_ok}")

    # Create or fix test user with proper whatsapp +50912345678
    user = User.query.filter_by(whatsapp='+50912345678').first()
    if not user:
        user = User(
            whatsapp='+50912345678',
            pseudo='testuser',
            name='Test User',
            auth_provider='whatsapp',
            is_active=True
        )
        db.session.add(user)
        print("Created new user +50912345678")

    user.set_password('123456')
    user.is_active = True
    db.session.commit()
    
    # Create Gkach account
    gk = UserGkach.query.filter_by(user_whatsapp='+50912345678').first()
    if not gk:
        gk = UserGkach(
            user_id=user.id,
            user_whatsapp='+50912345678',
            gkach_balance=2000
        )
        db.session.add(gk)
    else:
        gk.gkach_balance = max(gk.gkach_balance, 2000)
    db.session.commit()

    # Verify
    verify = User.query.filter_by(whatsapp='+50912345678').first()
    pw_ok = verify.check_password('123456') if verify else False
    gk_account = UserGkach.query.filter_by(user_whatsapp='+50912345678').first()
    print(f"\nVerification:")
    print(f"  User exists: {verify is not None}")
    print(f"  Password 123456 works: {pw_ok}")
    print(f"  Is active: {verify.is_active if verify else None}")
    print(f"  Gkach balance: {gk_account.gkach_balance if gk_account else 0}")
    
    # Also ensure charity account exists
    from app.services.gkach_service import GkachService
    try:
        GkachService.get_or_create_account('+509CHARITY')
        print("  Charity account +509CHARITY: OK")
    except Exception as e:
        print(f"  Charity account error: {e}")
