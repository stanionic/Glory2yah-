
import os
import sys
import uuid
import random
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models.user import User
from app.models.ad import Ad
from app.models.user_gkach import UserGkach


def main():
    app = create_app()
    with app.app_context():
        # 1. CREATE OR GET USER "StanD"
        user_whatsapp = "+50948592888"
        user_pseudo = "StanD"
        user_password = "081986"
        user_name = "StanD"
        
        user = User.query.filter_by(whatsapp=user_whatsapp).first()
        
        if not user:
            user = User(
                whatsapp=user_whatsapp,
                name=user_name,
                pseudo=user_pseudo,
                auth_provider="whatsapp",
                is_active=True,
                is_verified=True
            )
            user.set_password(user_password)
            db.session.add(user)
            db.session.commit()
            print(f"Created user {user_name} ({user_pseudo}) with WhatsApp: {user_whatsapp}")
        else:
            print(f"Found existing user {user.name} ({user.pseudo}) with WhatsApp: {user.whatsapp}")
        
        # 2. CREATE OR GET USER GKACH ACCOUNT
        user_gkach = UserGkach.query.filter_by(user_whatsapp=user_whatsapp).first()
        if not user_gkach:
            user_gkach = UserGkach(
                user_id=user.id,
                user_whatsapp=user_whatsapp,
                gkach_balance=5000
            )
            db.session.add(user_gkach)
            db.session.commit()
            print(f"Created Gkach account for {user_name} with balance: {user_gkach.gkach_balance} GKACH")
        
        # 3. ASSIGN ALL EXISTING ADS TO STAND
        all_ads = Ad.query.all()
        updated_count = 0
        for ad in all_ads:
            if ad.user_whatsapp != user_whatsapp:
                ad.user_whatsapp = user_whatsapp
                db.session.add(ad)
                updated_count += 1
        if updated_count > 0:
            db.session.commit()
            print(f"Updated {updated_count} existing ads to belong to {user_name}")
        else:
            print(f"All ads already belong to {user_name}")
        
        # 4. CREATE NEW ADS FROM ALL IMAGES IN static/uploads
        uploads_dir = os.path.join(os.path.dirname(__file__), "static", "uploads")
        image_files = []
        if os.path.exists(uploads_dir):
            for filename in os.listdir(uploads_dir):
                ext = os.path.splitext(filename)[1].lower()
                if ext in [".jpg", ".jpeg", ".png", ".gif"]:
                    image_files.append(filename)
        
        print(f"Found {len(image_files)} images in static/uploads")
        
        ad_templates = [
            {"title": "Bel Potre", "desc": "Potre atire bel tout moun, pote a la maison", "price_min": 1500, "price_max": 5000},
            {"title": "Atizay Dijital", "desc": "Atizay ki gen bon kalite, pou ou ki renmen atizay", "price_min": 2000, "price_max": 6000},
            {"title": "Koleksyon Mod", "desc": "Koleksyon mod ki byen konbine, pou tout okazyon", "price_min": 1000, "price_max": 4000},
            {"title": "Pwodui Bote", "desc": "Pwodui bote ki fe ou byen santi, tout kalite pou w chwazi", "price_min": 500, "price_max": 2500},
            {"title": "Manje Gourmand", "desc": "Manje ki gen bon gou, pou goumen ou", "price_min": 300, "price_max": 1500},
            {"title": "Liv Enteresan", "desc": "Liv ki fe ou aprann nouvo bagay, tout kalite", "price_min": 400, "price_max": 2000},
            {"title": "Jwet Pou Timoun", "desc": "Jwet ki fe timoun yo renmen, pwodui ki sekirite", "price_min": 600, "price_max": 3000},
            {"title": "Pwodui Machin", "desc": "Pwodui ki fe machin ou byen marche, bon kalite", "price_min": 800, "price_max": 4500},
            {"title": "Eleman Dekorasyon", "desc": "Eleman ki fe kay ou byen bel, pou tout go", "price_min": 1000, "price_max": 3500},
            {"title": "Akseswar Elektronik", "desc": "Akseswar ki fe telefòn ou menm byen itilize", "price_min": 700, "price_max": 3000},
        ]
        
        created_count = 0
        for idx, img_file in enumerate(image_files):
            existing_ad = Ad.query.filter_by(images=img_file, user_whatsapp=user_whatsapp).first()
            if existing_ad:
                continue
                
            template = random.choice(ad_templates)
            price = random.randint(template["price_min"], template["price_max"])
            view_count = random.randint(10, 200)
            like_count = random.randint(5, int(view_count * 0.8))
            star_count = random.randint(1, 5)
            days_ago = random.randint(0, 30)
            created_at = datetime.now() - timedelta(days=days_ago)
            
            ad = Ad(
                ad_id=str(uuid.uuid4()),
                user_whatsapp=user.whatsapp,
                title=template["title"] + f" #{idx+1}",
                description=template["desc"],
                ad_type="sell",
                price_gkach=price,
                admin_status="approved",
                images=img_file,
                view_count=view_count,
                like_count=like_count,
                star_count=star_count,
                share_count=random.randint(0, 20),
                created_at=created_at
            )
            
            db.session.add(ad)
            created_count += 1
            
            if (idx + 1) % 20 == 0:
                db.session.commit()
                print(f"Created {idx+1} ads so far...")
        
        if created_count > 0:
            db.session.commit()
        
        print("\nComplete! Here's your user info:")
        print(f"Name: {user_name}")
        print(f"Pseudo: {user_pseudo}")
        print(f"WhatsApp: {user_whatsapp}")
        print(f"Password: {user_password}")
        print(f"Gkach Balance: {user_gkach.gkach_balance} GKACH")
        print(f"Total ads created: {created_count}")
        print(f"Total ads assigned: {updated_count}")


if __name__ == "__main__":
    main()
