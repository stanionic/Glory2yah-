import os
import csv
from app import app, db, Ad

with app.app_context():
    ads = Ad.query.filter_by(admin_status='approved').all()
    os.makedirs('csv', exist_ok=True)
    for ad in ads:
        filename = f'csv/{ad.ad_id}.csv'
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Title', 'Description', 'Price', 'Image', 'URL'])
            url = f'http://localhost:5000/shopping_cart/{ad.ad_id}'
            # Get the first image URL for display
            first_image = ad.images.split(',')[0] if ad.images else ''
            image_url = f'http://localhost:5000/static/uploads/{first_image}' if first_image else ''
            writer.writerow([ad.title, ad.description, ad.price_gkach, image_url, url])
