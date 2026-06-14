
"""
Assign all existing ads to user with pseudo "+50948592888"
"""
import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models.user import User
from app.models.ad import Ad

def main():
    app = create_app()
    with app.app_context():
        # Get user by pseudo "+50948592888"
        user = User.query.filter_by(pseudo="+50948592888").first()
        if not user:
            print("User not found! Creating them...")
            user = User(
                name="Stanley",
                pseudo="+50948592888",
                whatsapp="+50948592888",
                is_active=True,
                is_admin=True
            )
            user.set_password("0886")
            db.session.add(user)
            db.session.commit()
            print(f"Created user {user.pseudo} with ID {user.id}")
        else:
            print(f"Found user {user.pseudo} with ID {user.id}")
        
        # Assign all existing ads to this user
        ads = Ad.query.all()
        updated_count = 0
        for ad in ads:
            if ad.user_whatsapp != user.whatsapp:
                print(f"Updating ad {ad.title} to belong to {user.pseudo}")
                ad.user_whatsapp = user.whatsapp
                updated_count += 1
        
        db.session.commit()
        print(f"\nTotal ads updated: {updated_count}")

if __name__ == "__main__":
    main()
