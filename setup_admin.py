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
        admin = User.query.filter_by(is_admin=True).first()
        
        if admin:
            print("Updating existing admin user...")
            admin.pseudo = "Admin509"
            admin.set_password("StanGlory2YahPub1986")
            admin.is_admin = True
            admin.is_active = True
        else:
            print("Creating new admin user...")
            admin = User(
                pseudo="Admin509",
                whatsapp="+50942882076",
                name="Admin509",
                is_admin=True,
                is_active=True
            )
            admin.set_password("StanGlory2YahPub1986")
            db.session.add(admin)
        
        db.session.commit()
        print("\nAdmin user setup complete!")
        print("=" * 50)
        print("Pseudo: Admin509")
        print("Password: StanGlory2YahPub1986")
        print("Admin: Yes")
        print("=" * 50)

if __name__ == '__main__':
    setup_admin()
