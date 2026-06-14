
"""
Create user StanD and add ads using existing media
"""
import os
import sys
import uuid
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models.user import User
from app.models.user_gkach import UserGkach
from app.models.ad import Ad

def main():
    app = create_app()
    with app.app_context():
        # 1. Create or get user "StanD"
        user = User.query.filter_by(pseudo="StanD").first()
        if not user:
            user = User(
                name="Stanley",
                pseudo="StanD",
                whatsapp="+50942882077",
                email="stan@glory2yah.com",
                is_active=True,
                is_admin=True,
                bio="Hello I'm StanD! Welcome to my page!"
            )
            user.set_password("StanGlory2YahPub1986")
            db.session.add(user)
            db.session.commit()
            print(f"Created user: StanD with ID {user.id}")
        else:
            print(f"User StanD already exists with ID {user.id}")
        
        # 2. Create or get UserGkach account
        user_gkach = UserGkach.query.filter_by(user_whatsapp=user.whatsapp).first()
        if not user_gkach:
            user_gkach = UserGkach(
                user_whatsapp=user.whatsapp,
                gkach_balance=10000  # Give them 10k Gkach
            )
            db.session.add(user_gkach)
            db.session.commit()
            print(f"Created Gkach account with balance {user_gkach.gkach_balance}")
        else:
            print(f"Gkach account already exists with balance {user_gkach.gkach_balance}")
        
        # 3. Get all existing media files in static/uploads, filter out payment/gkach/party/.gitkeep
        uploads_dir = os.path.join(app.root_path, '../static/uploads')
        uploads_dir = os.path.abspath(uploads_dir)
        media_files = []
        for filename in os.listdir(uploads_dir):
            if (filename.startswith(".") or 
                filename.startswith("gkach_") or 
                filename.startswith("payment_") or 
                filename.startswith("party_")):
                continue
            if any(filename.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.mp4', '.webm']):
                media_files.append(filename)
        
        print(f"Found {len(media_files)} media files to use!")
        
        # 4. Create ads from these files!
        ad_titles = [
            "Beautiful Portrait",
            "Fashion Collection",
            "Design Portfolio",
            "Art Work",
            "Photography Services",
            "Creative Projects",
            "Digital Art",
            "Graphic Design",
            "Event Photos",
            "Product Showcase"
        ]
        
        ad_descriptions = [
            "Check out this beautiful portrait available for purchase!",
            "Latest fashion collection - don't miss out!",
            "Professional design portfolio for review!",
            "Amazing art work for sale!",
            "Professional photography services available!",
            "Creative projects done with love!",
            "Original digital art pieces!",
            "High-quality graphic design services!",
            "Event photos from our latest gathering!",
            "Product showcase - see what we have to offer!"
        ]
        
        for i, media_file in enumerate(media_files):
            # Skip if ad already exists with this image
            existing = Ad.query.filter(Ad.images.like(f"%{media_file}%")).first()
            if existing:
                print(f"Skipping {media_file} - already has an ad!")
                continue
            
            # Create ad
            title = ad_titles[i % len(ad_titles)]
            description = ad_descriptions[i % len(ad_descriptions)]
            ad = Ad(
                ad_id=str(uuid.uuid4()),
                user_whatsapp=user.whatsapp,
                title=title,
                description=description,
                images=media_file,
                ad_type="sell",
                price_gkach=100 + (i * 50),
                admin_status="approved",
                payment_status="verified",
                view_count=10 + i,
                like_count=i*2,
                share_count=i
            )
            
            db.session.add(ad)
            print(f"Created ad: {title} (ID: {ad.ad_id})")
        
        # Commit all changes!
        db.session.commit()
        print("\nAll operations completed successfully!")

if __name__ == "__main__":
    main()
