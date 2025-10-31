import cv2
import numpy as np
from PIL import Image
import os

def extract_features(image_path):
    """Extract features from an image using ORB."""
    try:
        img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return None
        orb = cv2.ORB_create()
        keypoints, descriptors = orb.detectAndCompute(img, None)
        return descriptors
    except Exception as e:
        print(f"Error extracting features from {image_path}: {e}")
        return None

def find_similar_ads(query_image_path, threshold=0.7):
    """Find ads similar to the query image."""
    from app import app, db, Ad  # Import here to avoid circular import

    query_features = extract_features(query_image_path)
    if query_features is None:
        return []

    similar_ads = []
    with app.app_context():
        ads = Ad.query.filter_by(admin_status='approved').all()
        for ad in ads:
            if ad.media_type == 'video':
                # For videos, we could extract a frame, but for simplicity, skip or use thumbnail
                continue
            elif ad.media_type == 'images':
                image_paths = ad.images.split(',') if ad.images else []
                for img_path in image_paths:
                    full_path = os.path.join(app.config['UPLOAD_FOLDER'], img_path)
                    if os.path.exists(full_path):
                        ad_features = extract_features(full_path)
                        if ad_features is not None:
                            # Compute similarity using BFMatcher
                            bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
                            matches = bf.match(query_features, ad_features)
                            if len(matches) > 0:
                                # Calculate similarity score
                                similarity = len(matches) / max(len(query_features), len(ad_features))
                                if similarity >= threshold:
                                    similar_ads.append((ad, similarity))
                                    break  # Found a match, no need to check other images

    # Sort by similarity
    similar_ads.sort(key=lambda x: x[1], reverse=True)
    return [ad for ad, _ in similar_ads]
