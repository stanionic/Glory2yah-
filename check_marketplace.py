"""
Check and fix marketplace ads
This script will:
1. Check how many ads exist in the database
2. Show their approval status
3. Auto-approve ads if needed
"""
import sys
import os

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models.ad import Ad

app = create_app()

with app.app_context():
    print("=" * 60)
    print("MARKETPLACE ADS CHECKER")
    print("=" * 60)
    print()
    
    # Count total ads
    total_ads = Ad.query.count()
    print(f"Total ads in database: {total_ads}")
    
    if total_ads == 0:
        print("\n[INFO] No ads found in database.")
        print("You need to create ads first.")
        print("=" * 60)
        sys.exit(0)
    
    # Count by status
    approved = Ad.query.filter_by(admin_status='approved').count()
    pending = Ad.query.filter_by(admin_status='under_review').count()
    rejected = Ad.query.filter_by(admin_status='rejected').count()
    
    print(f"\nAds by status:")
    print(f"  - Approved: {approved}")
    print(f"  - Pending: {pending}")
    print(f"  - Rejected: {rejected}")
    
    # Show sample ads
    print(f"\nSample ads:")
    sample_ads = Ad.query.limit(5).all()
    for ad in sample_ads:
        images = ad.get_images_list()
        print(f"\n  ID: {ad.ad_id}")
        print(f"  Title: {ad.title if hasattr(ad, 'title') else 'N/A'}")
        print(f"  Description: {ad.description[:50] if ad.description else 'N/A'}...")
        print(f"  Status: {ad.admin_status}")
        print(f"  Price: {ad.price_gkach} Gkach")
        print(f"  Images: {len(images)} ({', '.join(images[:2])}...)")
        print(f"  Type: {ad.ad_type}")
    
    # Auto-approve if needed
    if approved == 0 and pending > 0:
        print("\n" + "=" * 60)
        print("AUTO-APPROVAL")
        print("=" * 60)
        response = input(f"\nWould you like to approve all {pending} pending ads? (yes/no): ")
        
        if response.lower() in ['yes', 'y']:
            pending_ads = Ad.query.filter_by(admin_status='under_review').all()
            for ad in pending_ads:
                ad.admin_status = 'approved'
                # Also approve payment if needed
                if ad.payment_status == 'pending':
                    ad.payment_status = 'approved'
            
            db.session.commit()
            print(f"\n[SUCCESS] Approved {len(pending_ads)} ads!")
            print("Marketplace should now display these ads.")
        else:
            print("\n[INFO] No ads approved.")
            print("Go to http://localhost:8080/admin to approve ads manually.")
    
    elif approved > 0:
        print(f"\n[SUCCESS] {approved} ads are approved and should appear in marketplace!")
        print("Visit: http://localhost:8080/mache")
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total ads: {total_ads}")
    print(f"Approved (visible in marketplace): {Ad.query.filter_by(admin_status='approved').count()}")
    print(f"Marketplace URL: http://localhost:8080/mache")
    print("=" * 60)
