"""Export-safe catalog builder for Meta/Facebook Ads.

This module is intentionally isolated and non-invasive: it reads only the
public, approved, sell-type ads already present in the app and prepares a
Meta-compatible payload without modifying existing app structure or templates.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from flask import current_app, url_for

from app.models.ad import Ad


def _image_url_for_ad(ad: Ad) -> Optional[str]:
    """Return the first image URL for a product when available."""
    try:
        images = ad.get_images_list() if hasattr(ad, 'get_images_list') else []
    except Exception:
        images = []

    if not images:
        return None

    image_name = images[0].strip()
    if not image_name:
        return None

    if image_name.startswith('http://') or image_name.startswith('https://'):
        return image_name

    try:
        return url_for('static', filename='uploads/' + image_name, _external=True)
    except Exception:
        base_url = (current_app.config.get('PUBLIC_BASE_URL') or '').rstrip('/')
        if base_url:
            return f"{base_url}/static/uploads/{image_name}"
        return f"/static/uploads/{image_name}"


def _product_url_for_ad(ad: Ad) -> str:
    """Return a stable public product URL."""
    try:
        return url_for('main.view_ad', ad_id=ad.ad_id, _external=True)
    except Exception:
        base_url = (current_app.config.get('PUBLIC_BASE_URL') or '').rstrip('/')
        path = f"/ad/{ad.ad_id}"
        return f"{base_url}{path}" if base_url else path


def get_approved_sell_ads_for_meta(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Return approved marketplace ads ready for Facebook catalog export."""
    query = Ad.query.filter_by(admin_status='approved', ad_type='sell').order_by(Ad.created_at.desc())
    if limit is not None:
        query = query.limit(limit)

    items: List[Dict[str, Any]] = []
    for ad in query.all():
        title = (getattr(ad, 'title', '') or '').strip()
        description = (getattr(ad, 'description', '') or '').strip()

        if not title or not description:
            continue

        price = getattr(ad, 'price_gkach', 0) or 0
        if price <= 0:
            continue

        image_url = _image_url_for_ad(ad)
        if not image_url:
            # Keep product in catalog only if it has a valid media asset or URL
            continue

        items.append({
            'id': getattr(ad, 'ad_id', ''),
            'title': title,
            'description': description[:240],
            'price': int(price),
            'currency': 'HTG',
            'category': getattr(ad, 'category', 'other') or 'other',
            'availability': 'in_stock',
            'condition': 'new',
            'brand': 'Glory2YahPub',
            'certified': bool(getattr(ad, 'is_certified', False)),
            'image_url': image_url,
            'product_url': _product_url_for_ad(ad),
            'ad_type': getattr(ad, 'ad_type', 'sell'),
            'admin_status': getattr(ad, 'admin_status', 'approved'),
            'created_at': ad.created_at.isoformat() if getattr(ad, 'created_at', None) else None,
        })

    return items


def build_meta_catalog_payload(limit: Optional[int] = None) -> Dict[str, Any]:
    """Build a Meta-friendly export payload without affecting the app structure."""
    ads = get_approved_sell_ads_for_meta(limit=limit)
    return {
        'generated_at': __import__('datetime').datetime.utcnow().isoformat() + 'Z',
        'source': 'approved_sell_ads',
        'count': len(ads),
        'ads': ads,
    }
