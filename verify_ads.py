
"""
Verify ads belong to user
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models.user import User
from app.models.ad import Ad

def main():
    app = create_app()
    with app.app_context():
        user = User.query.filter_by(pseudo="+50948592888").first()
        print(f"User: {user.pseudo}, WhatsApp: {user.whatsapp}")
        
        ads = Ad.query.filter_by(user_whatsapp=user.whatsapp).count()
        total_ads = Ad.query.count()
        print(f"Total ads in DB: {total_ads}")
        print(f"Ads owned by {user.pseudo}: {ads}")

if __name__ == "__main__":
    main()
