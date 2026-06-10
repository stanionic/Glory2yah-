"""
Create a test user for login testing
"""
from app import create_app, db
from app.models.user import User
from app.models.user_gkach import UserGkach

app = create_app()

with app.app_context():
    # Check if test user already exists
    existing = User.query.filter_by(pseudo='test').first()
    if existing:
        print('✅ Test user already exists')
        print(f'   Pseudo: test')
        print(f'   WhatsApp: {existing.whatsapp}')
        print(f'   Password: test1234')
    else:
        # Create test user
        user = User(
            whatsapp='+509XXXXXXXX1',
            pseudo='test',
            name='Test User',
            bio='Test account for login testing',
            auth_provider='whatsapp',
            is_active=True,
            email_verified=True,
            phone_verified=True
        )
        user.set_password('test1234')
        
        db.session.add(user)
        db.session.commit()
        
        # Create Gkach account
        user_gkach = UserGkach(
            user_id=user.id,
            user_whatsapp=user.whatsapp,
            gkach_balance=1000
        )
        db.session.add(user_gkach)
        db.session.commit()
        
        print('✅ Test user created successfully!')
        print(f'   Pseudo: test')
        print(f'   WhatsApp: +509XXXXXXXX1')
        print(f'   Password: test1234')
        print(f'   Gkach Balance: 1000')
        print()
        print('   Login at: http://localhost:8080/auth/login')
        print('   Use pseudo "test" or WhatsApp "+509XXXXXXXX1"')
