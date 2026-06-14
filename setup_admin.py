"""
Admin Setup Script for Glory2YahPub
Creates/updates the admin user
"""
import os
import sys
sys.path.insert(0, os.path.abspath('.'))

# Import all models to resolve relationships first
from app.models.user import User
from app.models.user_gkach import UserGkach
from app.models.ad import Ad
from app.models.delivery import Delivery
from app.models.batch import Batch
from app.models.batch_ad import BatchAd
from app.models.gkach_transaction import GkachTransaction

from app import create_app, db

def setup_admin():
    app = create_app('development')
    
    with app.app_context():
        # Check if admin already exists
        admin = User.query.filter_by(pseudo="+50942882076").first()
        
        if admin:
            print("Updating existing admin user...")
            admin.set_password("StanGlory2YahPub1986")
            admin.is_admin = True
            admin.is_active = True
            admin.whatsapp = "+50942882076"
            admin.name = "Stan Admin"
        else:
            print("Creating new admin user...")
            admin = User(
                pseudo="+50942882076",
                whatsapp="+50942882076",
                name="Stan Admin",
                is_admin=True,
                is_active=True
            )
            admin.set_password("StanGlory2YahPub1986")
            db.session.add(admin)
        
        db.session.commit()
        print("\n✅ Admin user setup complete!")
        print("=" * 50)
        print(f"📱 Pseudo: +50942882076")
        print(f"🔑 Password: StanGlory2YahPub1986")
        print(f"📧 WhatsApp: +50942882076")
        print(f"⚡ Admin: Yes")
        print("=" * 50)

if __name__ == '__main__':
    setup_admin()
