from app import create_app, db
from app.models.user import User
from app.models.user_gkach import UserGkach

app = create_app()

with app.app_context():
    # Create a test user
    test_whatsapp = "123456"
    test_pseudo = "testuser"
    test_name = "Test User"
    test_password = "123456"
    
    # Check if user already exists
    existing = User.query.filter_by(whatsapp=test_whatsapp).first()
    if existing:
        print(f"Test user already exists: {test_pseudo}")
        print(f"Password: {test_password}")
        exit(0)
    
    # Create user
    user = User(
        whatsapp=test_whatsapp,
        pseudo=test_pseudo,
        name=test_name,
        auth_provider='whatsapp',
        is_active=True
    )
    user.set_password(test_password)
    
    db.session.add(user)
    db.session.commit()
    
    # Create Gkach account
    user_gkach = UserGkach(
        user_id=user.id,
        user_whatsapp=test_whatsapp,
        gkach_balance=1000  # Give some test GKACH
    )
    db.session.add(user_gkach)
    db.session.commit()
    
    print("Test user created successfully!")
    print(f"Pseudo: {test_pseudo}")
    print(f"Password: {test_password}")
    print(f"WhatsApp: {test_whatsapp}")