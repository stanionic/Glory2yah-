"""
Import existing images from uploads folder as ads
This will create ad entries in the database for all images in static/uploads/
"""
import sys
import os
import uuid
from datetime import datetime

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models.ad import Ad

app = create_app()

with app.app_context():
    print("=" * 60)
    print("IMPORT IMAGES AS ADS")
    print("=" * 60)
    print()
    
    # Check uploads folder
    uploads_dir = 'static/uploads'
    if not os.path.exists(uploads_dir):
        print(f"[ERROR] Uploads folder not found: {uploads_dir}")
        sys.exit(1)
    
    # Get all image files
    image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.webp')
    all_files = os.listdir(uploads_dir)
    image_files = [f for f in all_files if f.lower().endswith(image_extensions)]
    
    # Filter out payment and gkach images
    product_images = [f for f in image_files 
                     if not f.startswith('payment_') 
                     and not f.startswith('gkach_')
                     and not f.startswith('party_')]
    
    print(f"Found {len(product_images)} product images in uploads folder")
    
    if len(product_images) == 0:
        print("\n[INFO] No product images found to import.")
        print("Upload some images to static/uploads/ first.")
        sys.exit(0)
    
    # Show sample
    print(f"\nSample images:")
    for img in product_images[:5]:
        print(f"  - {img}")
    if len(product_images) > 5:
        print(f"  ... and {len(product_images) - 5} more")
    
    # Auto-import (no confirmation needed)
    print("\n" + "=" * 60)
    print(f"Importing {len(product_images)} images as ads...")
    print("=" * 60)
    
    # Import images as ads
    print("\n[INFO] Importing images...")
    
    # Group images (every 3 images = 1 ad)
    ads_created = 0
    batch_size = 3
    
    for i in range(0, len(product_images), batch_size):
        batch = product_images[i:i+batch_size]
        
        # Create ad
        ad_id = str(uuid.uuid4())
        images_str = ','.join(batch)
        
        # Generate title and description based on image name
        first_image = batch[0]
        base_name = os.path.splitext(first_image)[0]
        # Remove UUID prefix if present
        if '_' in base_name:
            parts = base_name.split('_', 1)
            if len(parts) > 1:
                base_name = parts[1]
        
        title = f"Pwodui {ads_created + 1}"
        description = f"Pwodui kalite siperyè disponib kounye a. Imaj: {base_name}"
        
        # Random price between 50-500 Gkach
        import random
        price = random.randint(5, 50) * 10
        
        new_ad = Ad(
            ad_id=ad_id,
            user_whatsapp='+50942882076',  # Default admin number
            title=title,
            description=description,
            media_type='images',
            images=images_str,
            video=None,
            ad_type='sell',
            price_gkach=price,
            admin_status='approved',  # Auto-approve
            payment_status='approved',
            created_at=datetime.utcnow()
        )
        
        db.session.add(new_ad)
        ads_created += 1
        
        if ads_created % 10 == 0:
            print(f"  Imported {ads_created} ads...")
    
    # Commit all
    db.session.commit()
    
    print(f"\n[SUCCESS] Imported {ads_created} ads!")
    print(f"\nThese ads are now visible in:")
    print(f"  - Home feed: http://localhost:8080")
    print(f"  - Marketplace: http://localhost:8080/mache")
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Images found: {len(product_images)}")
    print(f"Ads created: {ads_created}")
    print(f"Status: All approved and visible")
    print("=" * 60)
