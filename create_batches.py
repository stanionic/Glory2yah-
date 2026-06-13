"""
Create batches from existing ads
Groups ads into batches of 5 for the home feed
"""
import sys
import os
import uuid
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models.ad import Ad
from app.models.batch import Batch
from app.models.batch_ad import BatchAd

app = create_app()

with app.app_context():
    print("=" * 60)
    print("CREATE BATCHES FROM ADS")
    print("=" * 60)
    print()
    
    # Get all approved ads
    all_ads = Ad.query.filter_by(admin_status='approved').all()
    print(f"Total approved ads: {len(all_ads)}")
    
    if len(all_ads) == 0:
        print("\n[ERROR] No approved ads found.")
        sys.exit(1)
    
    # Delete existing batches
    existing_batches = Batch.query.count()
    if existing_batches > 0:
        print(f"\nDeleting {existing_batches} existing batches...")
        BatchAd.query.delete()  # Clean up junction table first
        Batch.query.delete()
        db.session.commit()
    
    # Create batches of 5
    print(f"\nCreating batches of 5 ads...")
    batches_created = 0
    
    for i in range(0, len(all_ads), 5):
        batch_ads = all_ads[i:i+5]
        
        if len(batch_ads) < 5:
            print(f"\n[INFO] Skipping incomplete batch with {len(batch_ads)} ads")
            continue
        
        # Create batch
        batch_id = str(uuid.uuid4())
        
        new_batch = Batch(
            batch_id=batch_id,
            created_at=datetime.utcnow()
        )
        db.session.add(new_batch)
        
        # Create junction entries with ordering and update ad references
        for idx, ad in enumerate(batch_ads):
            junction = BatchAd(batch_id=batch_id, ad_id=ad.ad_id, position=idx)
            db.session.add(junction)
            ad.batch_id = batch_id
        
        batches_created += 1
        
        print(f"  Batch {batches_created}: {len(batch_ads)} ads")
    
    db.session.commit()
    
    print(f"\n[SUCCESS] Created {batches_created} batches!")
    
    # Show latest batch
    latest_batch = Batch.query.order_by(Batch.created_at.desc()).first()
    if latest_batch:
        print(f"\nLatest batch ID: {latest_batch.batch_id}")
        print(f"Ads in latest batch: {latest_batch.batch_ads.count()}")
        print(f"\nThis batch will be displayed on the home page!")
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total ads: {len(all_ads)}")
    print(f"Batches created: {batches_created}")
    print(f"Ads per batch: 5")
    print(f"Home page will show: Latest batch (5 ads)")
    print(f"Marketplace will show: All {len(all_ads)} ads")
    print("=" * 60)
