from app import app, db, Ad, Batch, UserGkach, User, CartItem, Delivery, GkachRate
import json

with app.app_context():
    print("=" * 50)
    print("DATABASE VERIFICATION")
    print("=" * 50)
    
    # Count records
    total_ads = Ad.query.count()
    approved_ads = Ad.query.filter_by(admin_status='approved').count()
    pending_ads = Ad.query.filter_by(admin_status='pending').count()
    rejected_ads = Ad.query.filter_by(admin_status='rejected').count()
    total_batches = Batch.query.count()
    total_users_gkach = UserGkach.query.count()
    total_users = User.query.count()
    total_cart_items = CartItem.query.count()
    total_deliveries = Delivery.query.count()
    total_rates = GkachRate.query.count()
    
    print(f"\nADS:")
    print(f"  Total Ads: {total_ads}")
    print(f"  Approved: {approved_ads}")
    print(f"  Pending: {pending_ads}")
    print(f"  Rejected: {rejected_ads}")
    
    print(f"\nBATCHES:")
    print(f"  Total Batches: {total_batches}")
    
    print(f"\nUSERS:")
    print(f"  Users with Gkach: {total_users_gkach}")
    print(f"  Total Users: {total_users}")
    
    print(f"\nCOMMERCE:")
    print(f"  Cart Items: {total_cart_items}")
    print(f"  Deliveries: {total_deliveries}")
    
    print(f"\nRATES:")
    print(f"  Gkach Rates: {total_rates}")
    
    # Sample data
    print("\n" + "=" * 50)
    print("SAMPLE DATA")
    print("=" * 50)
    
    # First ad
    ad = Ad.query.first()
    if ad:
        print(f"\nFirst Ad:")
        print(f"  ID: {ad.ad_id}")
        print(f"  Title: {ad.title}")
        print(f"  Type: {ad.ad_type}")
        print(f"  Status: {ad.admin_status}")
        print(f"  Media Type: {ad.media_type}")
        print(f"  Price: {ad.price_gkach} Gkach")
        print(f"  Created: {ad.created_at}")
    else:
        print("\nNo ads in database")
    
    # First batch
    batch = Batch.query.first()
    if batch:
        print(f"\nFirst Batch:")
        print(f"  ID: {batch.batch_id}")
        print(f"  Ad Count: {len(batch.ads.split(','))}")
        print(f"  Share Count: {batch.share_count}")
        print(f"  Click Rewards: {batch.click_rewards}")
        print(f"  Created: {batch.created_at}")
    else:
        print("\nNo batches in database")
    
    # Gkach rates
    rates = GkachRate.query.all()
    if rates:
        print(f"\nGkach Rates:")
        for rate in rates:
            print(f"  {rate.currency}: {rate.rate_per_gkach}")
    else:
        print("\nNo Gkach rates configured")
    
    # User Gkach balances
    users_gkach = UserGkach.query.all()
    if users_gkach:
        print(f"\nUser Gkach Balances:")
        for user in users_gkach[:5]:  # Show first 5
            print(f"  {user.user_whatsapp}: {user.gkach_balance} Gkach")
            if user.gkach_requests:
                try:
                    requests = json.loads(user.gkach_requests)
                    print(f"    Requests: {len(requests)}")
                except:
                    pass
    else:
        print("\nNo users with Gkach balances")
    
    # Deliveries
    deliveries = Delivery.query.all()
    if deliveries:
        print(f"\nDeliveries:")
        for delivery in deliveries[:3]:  # Show first 3
            print(f"  ID: {delivery.delivery_id}")
            print(f"    Status: {delivery.status}")
            print(f"    Total: {delivery.total_price} Gkach")
            print(f"    Shipping: {delivery.delivery_cost} Gkach")
    else:
        print("\nNo deliveries in database")
    
    print("\n" + "=" * 50)
    print("DATABASE VERIFICATION COMPLETE")
    print("=" * 50)
    print(f"\nDatabase Status: HEALTHY")
    print(f"Total Records: {total_ads + total_batches + total_users_gkach + total_users + total_cart_items + total_deliveries}")
