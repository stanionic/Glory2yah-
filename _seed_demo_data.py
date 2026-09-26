"""Glory2YahPub demo data seed for video production.
Seeds realistic APPROVED sell products (marketplace), publish posts (feed),
and a demo seller user with Gkach balance using EXISTING real upload images.
Idempotent: only inserts if ad_id not present.
"""
import os, sys
sys.path.insert(0, os.path.abspath('.'))
from app import create_app, db
from app.models.ad import Ad
from app.models.user import User
from app.models.user_gkach import UserGkach
from app.utils.currency import htg_to_gkach

app = create_app('development')

# Pick real existing images from static/uploads (verified above)
IMGS = {
    'food':  ['3cf898ad-492a-4798-b53b-f25f8a6ed32d_IMG-20250918-WA0001.jpg',
              '2c082020-c64a-46c4-b418-faec446e39e5_IMG-20250918-WA0005.jpg',
              '7d68a8e7-ed49-4895-8c13-9096c3787c48_IMG-20250918-WA0006.jpg'],
    'fashion': ['1ef6a721-36b2-4f61-8c65-9e077ade834b_IMG-20250918-WA0003.jpg',
                '2bb35744-b6da-4721-9d33-c5714b5029ab_IMG-20250918-WA0004.jpg',
                '0c0a0f9b-3a25-4fca-87df-cab59ab37585_IMG-20250918-WA0003.jpg'],
    'electronics': ['73dd6277-8ca7-4d93-9263-d6ae98da5e30_WhatsApp_Image_2025-02-20_at_16.14.43_0a75676e.jpg',
                    '1e557b50-7e0e-4c4a-91bd-71995fb6166e_WhatsApp_Image_2025-02-20_at_16.53.18_645cf06e.jpg'],
    'beauty':  ['2d84470e-3ef6-44e8-9d51-3f6843b29bd6_IMG-20250918-WA0002.jpg',
                '049aa55d-7b0a-4352-83d5-d8d11cad4263_IMG-20250918-WA0002.jpg'],
    'home':    ['85a21894-185b-428c-8715-d67d90699151_WhatsApp_Image_2025-10-18_at_08.50.02_1ec9a08c.jpg',
                '0dbba1a4-42b7-4f3c-af02-1b46a2e565e7_WhatsApp_Image_2025-10-18_at_08.50.02_1ec9a08c.jpg'],
    'other':   ['8a0a9376-3811-4dfe-ad08-6fb6d4e79129_360_F_305138768_MjmFQI9ZfW6jLcJHgpqJs2rqH0a5FZzR.jpg',
                '9f89fc1a-1af3-4835-84bf-ea2665f50946_6VJMRTA6-default-Q9HBBC.jpg'],
}

# Products: (ad_id, title, desc, category, price_htg, qty, img_key)
PRODUCTS = [
    ('DEMO-SELL-001', 'Sable Kaseròl 3kg — Manje Ayisyen', 'Sable fre dirak soti jaden, pakèt 3 kg. Ide pou gratin, mayi moulen ak labouyi. Livrezon zòn PAP disponib.', 'food', 250, 20, 'food'),
    ('DEMO-SELL-002', 'Lamayi Modèn Fanm — Mòd', 'Bèl lamayi modèn, twal byen chwazi, plizyè koulè disponib. Fèt ak presizyon, kòrèk pou tout fèt.', 'fashion', 1800, 5, 'fashion'),
    ('DEMO-SELL-003', 'Téléfòn Andwoid 128GB', 'Telefon andwoid neuf, 128GB, 6GB RAM, bon kamera. Garanti 3 mwa. Pri negociab.', 'electronics', 8500, 3, 'electronics'),
    ('DEMO-SELL-004', 'Kòsmetik Natirèl — Twous 12 moso', 'Twous kòsmetik natirèl pou swen po, san pwodui chimik danjere. Ide pou don oswa pou tèt ou.', 'beauty', 900, 8, 'beauty'),
    ('DEMO-SELL-005', 'Mèb Salon — Chèz + Tab', 'Mèb salon konplè, bwa solid, fini bèl. Livrezon ak enstalasyon disponib.', 'home', 15000, 2, 'home'),
    ('DEMO-SELL-006', 'Machandiz Divès — Lòt', 'Divès machandiz nan bon pri, pèfè pou revandè. Mo kadejak disponib.', 'other', 3000, 10, 'other'),
]

POSTS = [
    ('DEMO-PUB-001', 'Nouvo Fonksyonalite nan Glory2YahPub', 'Jodi a nou lage Marketplatz neuf la! Kounye a ou ka achte ak vande dirèkteman nan app la. Vin dekouvri!', 'publish'),
    ('DEMO-PUB-002', 'Kijan ou ka genyen Gkach?', 'Pataje piblisite yo, envite zanmi ou, epi genyen Gkach chak fwa. Gkach se monnen entèn nan Glory2YahPub pou achte nan mache a.', 'publish'),
]

with app.app_context():
    # Ensure demo seller user exists
    seller = User.query.filter_by(whatsapp='+50937000001').first()
    if not seller:
        seller = User(whatsapp='+50937000001', pseudo='DemoShop', name='Demo Shop G2Y',
                      auth_provider='whatsapp', is_active=True, is_admin=False)
        seller.set_password('demo123')
        db.session.add(seller)
        db.session.flush()
        gk = UserGkach(user_id=seller.id, user_whatsapp=seller.whatsapp, gkach_balance=5000)
        db.session.add(gk)
        db.session.commit()
        print('Created demo seller + Gkach account')
    else:
        print('Demo seller exists')

    # Seed products
    for (aid, title, desc, cat, price_htg, qty, ikey) in PRODUCTS:
        if Ad.query.filter_by(ad_id=aid).first():
            print(f'  exists: {aid}')
            continue
        if ikey not in IMGS:
            print(f'  skip (no img): {aid}')
            continue
        imgs = ','.join(IMGS[ikey][:2])
        price_g = htg_to_gkach(price_htg)
        ad = Ad(ad_id=aid, user_whatsapp=seller.whatsapp, title=title, description=desc,
                category=cat, ad_type='sell', media_type='images', images=imgs,
                price_gkach=price_g, quantity=qty, admin_status='approved',
                payment_status='verified', publish_fee_gkach=1000,
                like_count=5, star_count=3, view_count=120, share_count=2)
        db.session.add(ad)
        print(f'  + product: {aid} ({price_g} Gkach)')

    # Seed publish posts
    for (aid, title, desc, atype) in POSTS:
        if Ad.query.filter_by(ad_id=aid).first():
            print(f'  exists: {aid}')
            continue
        ad = Ad(ad_id=aid, user_whatsapp=seller.whatsapp, title=title, description=desc,
                category='other', ad_type='publish', media_type='text',
                admin_status='approved', payment_status='completed',
                like_count=3, star_count=0, view_count=45, share_count=1)
        db.session.add(ad)
        print(f'  + post: {aid}')

    db.session.commit()
    print('Seeding complete.')

    # Report counts
    from app.models.ad import Ad as A
    print('APPROVED sell:', A.query.filter_by(admin_status='approved', ad_type='sell').count())
    print('APPROVED publish:', A.query.filter_by(admin_status='approved', ad_type='publish').count())
    print('Total ads:', A.query.count())
