
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
        # Verify user exists
        user_whatsapp = "+50942882076"
        user = User.query.filter_by(whatsapp=user_whatsapp).first()
        print(f"User found: {user.name if user else 'NOT FOUND'}")
        
        # Count user's ads
        ad_count = Ad.query.filter_by(user_whatsapp=user_whatsapp).count()
        print(f"Number of ads for StanD: {ad_count}")
        
        # Show 5 ads
        ads = Ad.query.filter_by(user_whatsapp=user_whatsapp).limit(5).all()
        print("\nSample ads:")
        for ad in ads:
            print(f"- {ad.title} | {ad.price_gkach} GKach | {ad.images}")


if __name__ == "__main__":
    main()
