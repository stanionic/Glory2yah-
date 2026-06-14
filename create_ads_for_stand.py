
import os
import sys
import uuid
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models.user import User
from app.models.ad import Ad
from werkzeug.security import generate_password_hash
import random
from datetime import datetime, timedelta


def main():
    app = create_app()
    with app.app_context():
        # 1. Create or get the user "StanD"
        user_whatsapp = "+50942882076"
        user = User.query.filter_by(whatsapp=user_whatsapp).first()
        
        if not user:
            user = User(
                whatsapp=user_whatsapp,
                name="StanD",
                password=generate_password_hash("0886"),
                is_verified=True
            )
            db.session.add(user)
            db.session.commit()
            print(f"Created user StanD with whatsapp {user_whatsapp}")
        else:
            print(f"User StanD already exists with id {user.id}")
            
        # 2. Get all images from static/uploads (filter images only)
        uploads_dir = os.path.join(os.path.dirname(__file__), "static", "uploads")
        image_files = []
        
        for filename in os.listdir(uploads_dir):
            ext = os.path.splitext(filename)[1].lower()
            if ext in [".jpg", ".jpeg", ".png", ".gif"]:
                image_files.append(filename)
        
        print(f"Found {len(image_files)} images in static/uploads")
        
        # 3. Ad templates
        ad_templates = [
            {"title": "Bèl Pòtre", "desc": "Pòtre atire bèl tout moun, pote a la maison", "cat": "home", "price_min": 1500, "price_max": 5000},
            {"title": "Atizay Dijital", "desc": "Atizay ki gen bon kalite, pou ou ki renmen atizay", "cat": "electronics", "price_min": 2000, "price_max": 6000},
            {"title": "Koleksyon Mòd", "desc": "Koleksyon mòd ki byen konbine, pou tout okazyon", "cat": "fashion", "price_min": 1000, "price_max": 4000},
            {"title": "Pwodui Bote", "desc": "Pwodui bote ki fè ou byen santi, tout kalite pou w chwazi", "cat": "beauty", "price_min": 500, "price_max": 2500},
            {"title": "Manje Gourmand", "desc": "Manje ki gen bon gou, pou goumen ou", "cat": "food", "price_min": 300, "price_max": 1500},
            {"title": "Liv Entérésan", "desc": "Liv ki fè ou aprann nouvo bagay, tout kalite", "cat": "books", "price_min": 400, "price_max": 2000},
            {"title": "Jwèt Pou Timoun", "desc": "Jwèt ki fè timoun yo renmen, pwodui ki sekirite", "cat": "toys", "price_min": 600, "price_max": 3000},
            {"title": "Pwodui Machin", "desc": "Pwodui ki fè machin ou byen marche, bon kalite", "cat": "automotive", "price_min": 800, "price_max": 4500},
            {"title": "Eleman Dekorasyon", "desc": "Eleman ki fè kay ou byen bèl, pou tout go", "cat": "home", "price_min": 1000, "price_max": 3500},
            {"title": "Akseswar Elektronik", "desc": "Akseswar ki fè telefòn ou menm byen itilize", "cat": "electronics", "price_min": 700, "price_max": 3000},
        ]
        
        # 4. Create ads using the images
        created_count = 0
        
        for idx, img_file in enumerate(image_files):
            # Pick a random template
            template = random.choice(ad_templates)
            
            # Generate price
            price = random.randint(template["price_min"], template["price_max"])
            
            # Generate random view/like/star counts
            view_count = random.randint(10, 200)
            like_count = random.randint(5, int(view_count * 0.8))
            star_count = random.randint(1, 5)
            rating = random.randint(3, 5)
            
            # Created date (random in last 30 days)
            days_ago = random.randint(0, 30)
            created_at = datetime.now() - timedelta(days=days_ago)
            
            # Create ad
            ad = Ad(
                ad_id=str(uuid.uuid4()),
                user_whatsapp=user.whatsapp,
                title=template["title"] + f" #{idx+1}",
                description=template["desc"],
                ad_type="sell",
                price_gkach=price,
                admin_status="approved",
                images=img_file,  # Use the image
                view_count=view_count,
                like_count=like_count,
                star_count=star_count,
                share_count=random.randint(0, 20),
                created_at=created_at
            )
            
            db.session.add(ad)
            created_count += 1
            
            # Commit every 20 ads to prevent issues
            if (idx + 1) % 20 == 0:
                db.session.commit()
                print(f"Created {idx+1} ads so far...")
        
        # Final commit
        db.session.commit()
        
        print(f"\nAll done! Created {created_count} ads for StanD!")
        print(f"User: {user.name}, WhatsApp: {user.whatsapp}")
        print(f"Password: 0886")


if __name__ == "__main__":
    main()
