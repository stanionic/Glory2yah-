
import os
import sys
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models.ad import Ad


def main():
    app = create_app()
    with app.app_context():
        print("=== Ads in Database ===")
        ads = Ad.query.order_by(Ad.created_at.desc()).limit(10).all()
        for i, ad in enumerate(ads, 1):
            print(f"\n{i}. {ad.title}")
            print(f"   ID: {ad.ad_id}")
            print(f"   Seller: {ad.user_whatsapp}")
            print(f"   Type: {ad.ad_type}")
            print(f"   Price: {ad.price_gkach} GKach")
            print(f"   Status: {ad.admin_status}")
            print(f"   Created: {ad.created_at}")
            print(f"   Views: {ad.view_count} | Likes: {ad.like_count}")
        
        print(f"\n=== Total Ads: {Ad.query.count()} ===")
        
        stats = {
            'approved': Ad.query.filter_by(admin_status='approved').count(),
            'pending': Ad.query.filter_by(admin_status='under_review').count(),
            'rejected': Ad.query.filter_by(admin_status='rejected').count(),
        }
        print(f"Approved: {stats['approved']} | Pending: {stats['pending']} | Rejected: {stats['rejected']}")


if __name__ == "__main__":
    main()

