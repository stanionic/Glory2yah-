"""
Script pour créer des ADS de test (Sell & Publish) avec le compte test
Utilisateur test: +50912345678 / 123456
"""
import sys
import os
import uuid
from datetime import datetime

# Ajouter le répertoire courant au path
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app, db
from app.models.user import User
from app.models.user_gkach import UserGkach
from app.models.ad import Ad
from app.models.batch import Batch
from app.models.batch_ad import BatchAd

app = create_app()

# Données pour les ADS de type "sell" (produits à vendre)
SELL_ADS = [
    {
        'title': 'Bib LaSante 2024 - Livre Neuf',
        'description': 'Bib LaSante edisyon 2024 an kreyòl. Liv nan bon eta, papye blanch. Pri a 150 Gkach. Disponib tou nan fòma PDF.',
        'ad_type': 'sell',
        'price_gkach': 150,
        'media_type': 'text'
    },
    {
        'title': 'Vè bòbine orijinal - Tradisyonèl',
        'description': 'Vè bòbine tradisyonèl ayisyen. Manyèl travay, bèl fini. Disponib nan tout koulè. Pri a 50 Gkach chak.',
        'ad_type': 'sell',
        'price_gkach': 50,
        'media_type': 'text'
    },
    {
        'title': 'Videyo Muzik Gospel - Glory2Yah',
        'description': 'Videyo mizik Gospel Glory2YahPub. Videyo kalite HD, dire 5 minit. Pri a 200 Gkach.',
        'ad_type': 'sell',
        'price_gkach': 200,
        'media_type': 'text'
    },
    {
        'title': 'Fèy Manyòk - Pake 5kg',
        'description': 'Fèy manyòk fre, dirèk soti jaden. Pake 5kg. Pri a 75 Gkach. Livrezon disponib.',
        'ad_type': 'sell',
        'price_gkach': 75,
        'media_type': 'text'
    },
    {
        'title': 'Savon Vè bòbine natirèl - Pakè 3',
        'description': 'Savon natirèl fèt ak vè bòbine. Pakè 3 savon. Bon pou po a. Pri a 100 Gkach.',
        'ad_type': 'sell',
        'price_gkach': 100,
        'media_type': 'text'
    },
    {
        'title': 'Tablo Penti Glory - Dekorasyon',
        'description': 'Tablo penti Glory fèt alamen. Dekorasyon kay. Dimansyon 40x50cm. Pri a 300 Gkach.',
        'ad_type': 'sell',
        'price_gkach': 300,
        'media_type': 'text'
    },
    {
        'title': 'Videyo Fòmasyon Jadinaj',
        'description': 'Videyo fòmasyon sou jadinaj òganik. Aprepram plante legim ak fèy. Pri a 120 Gkach.',
        'ad_type': 'sell',
        'price_gkach': 120,
        'media_type': 'text'
    },
    {
        'title': 'Chapo pay tradisyonèl - Fèt alamen',
        'description': 'Chapo pay tradisyonèl ayisyen. Fèt alamen ak anpil swen. Disponib nan tout gwosè. Pri a 80 Gkach.',
        'ad_type': 'sell',
        'price_gkach': 80,
        'media_type': 'text'
    }
]

# Données pour les ADS de type "publish" (publications sociales)
PUBLISH_ADS = [
    {
        'title': 'Vèsè Jou a - Jan 3:16',
        'description': 'Paske Bondye te sitèlman renmen lemon, ke li bay sèl Pitit li, pou tout moun ki kwè nan li pa peri, men pou yo gen lavi etènèl.',
        'ad_type': 'publish',
        'price_gkach': 0,
        'media_type': 'text'
    },
    {
        'title': 'Konsèy pou Jadinaj',
        'description': 'Konsèy pratik pou jadinaj: plante nan sezon lapli, itilize konpòs natirèl, ak wotasyon rekòt. Pataje konesans ou nan komantè yo!',
        'ad_type': 'publish',
        'price_gkach': 0,
        'media_type': 'text'
    },
    {
        'title': 'Nouvèl Glory2YahPub',
        'description': 'Byenveni nan Glory2YahPub! Nou ap devlope fonksyonalite nouvo pou sèvi ou pi byen. Swiv nou pou mizajou yo.',
        'ad_type': 'publish',
        'price_gkach': 0,
        'media_type': 'text'
    },
    {
        'title': 'Edikasyon Finansye',
        'description': 'Kèk prensip edikasyon finansye: 1) Epargne 10% revni ou, 2) Envesti nan sa ou konprann, 3) Evite dèt ki pa nesesè.',
        'ad_type': 'publish',
        'price_gkach': 0,
        'media_type': 'text'
    },
    {
        'title': 'Resèt: Soup Joumou',
        'description': 'Resèt soup joumou tradisyonèl: 1) Koupe joumou an moso, 2) Mete vyann bèf, 3) Ajoute legim, 4) Kuit pandan 2 èdtan. Bon apeti!',
        'ad_type': 'publish',
        'price_gkach': 0,
        'media_type': 'text'
    }
]


def create_ads():
    """Créer les ADS de test"""
    with app.app_context():
        print("=" * 60)
        print("CRÉATION DES ADS DE TEST")
        print("=" * 60)
        
        # Trouver l'utilisateur test
        test_user = User.query.filter_by(whatsapp='+50912345678').first()
        if not test_user:
            print("[ERREUR] Utilisateur test '+50912345678' pa jwenn!")
            print("Kreye kont test avan:")
            print("  python create_test_user.py")
            return False
        
        print(f"\n[OK] Itilizatè test jwenn: {test_user.pseudo} (ID: {test_user.id})")
        
        # Vérifier le solde Gkach
        test_gkach = UserGkach.query.filter_by(user_whatsapp=test_user.whatsapp).first()
        if test_gkach:
            print(f"[OK] Balans Gkach: {test_gkach.gkach_balance}")
        else:
            # Créer un compte Gkach si pas existant
            test_gkach = UserGkach(
                user_id=test_user.id,
                user_whatsapp=test_user.whatsapp,
                gkach_balance=1000
            )
            db.session.add(test_gkach)
            db.session.commit()
            print(f"[OK] Nouvo kont Gkach kreye ak 1000 Gkach")
        
        # Supprimer les anciennes ADS de test si existent
        old_ads = Ad.query.filter_by(user_whatsapp=test_user.whatsapp).all()
        if old_ads:
            print(f"\n[INFO] Efase {len(old_ads)} ansyen ADS...")
            for ad in old_ads:
                db.session.delete(ad)
            db.session.commit()
        
        # Créer les ADS de type "sell"
        print(f"\n--- CREATION ADS SELL ({len(SELL_ADS)}) ---")
        created_sell = 0
        for ad_data in SELL_ADS:
            try:
                ad = Ad(
                    ad_id=str(uuid.uuid4()),
                    user_whatsapp=test_user.whatsapp,
                    title=ad_data['title'],
                    description=ad_data['description'],
                    media_type=ad_data.get('media_type', 'text'),
                    ad_type=ad_data['ad_type'],
                    price_gkach=ad_data['price_gkach'],
                    admin_status='approved',  # Auto-approuvé pour test
                    payment_status='completed'
                )
                db.session.add(ad)
                created_sell += 1
                print(f"  [OK] {ad_data['title']} - {ad_data['price_gkach']} Gkach")
            except Exception as e:
                print(f"  [ERR] {ad_data['title']}: {e}")
        
        # Créer les ADS de type "publish"
        print(f"\n--- CREATION ADS PUBLISH ({len(PUBLISH_ADS)}) ---")
        created_publish = 0
        for ad_data in PUBLISH_ADS:
            try:
                ad = Ad(
                    ad_id=str(uuid.uuid4()),
                    user_whatsapp=test_user.whatsapp,
                    title=ad_data['title'],
                    description=ad_data['description'],
                    media_type=ad_data.get('media_type', 'text'),
                    ad_type=ad_data['ad_type'],
                    price_gkach=0,
                    admin_status='approved',  # Auto-approuvé pour test
                    payment_status='completed'
                )
                db.session.add(ad)
                created_publish += 1
                print(f"  [OK] {ad_data['title']}")
            except Exception as e:
                print(f"  [ERR] {ad_data['title']}: {e}")
        
        # Commit toutes les ADS
        db.session.commit()
        total_created = created_sell + created_publish
        print(f"\n{'=' * 60}")
        print(f"RÉSUMÉ:")
        print(f"  Total ADS créées: {total_created}")
        print(f"  - Sell: {created_sell}")
        print(f"  - Publish: {created_publish}")
        print(f"  Itilizatè: {test_user.pseudo} (WhatsApp: {test_user.whatsapp})")
        print(f"  Mot de passe: 123456")
        print(f"{'=' * 60}")
        
        # Créer un batch avec les 5 premières ADS sell pour l'affichage
        print(f"\n--- CREATION BATCH PUBLICITAIRE ---")
        try:
            from app.models.batch import Batch
            from app.models.batch_ad import BatchAd
            
            # Prendre les 5 premières ADS sell pour le batch
            sell_ads = Ad.query.filter_by(
                user_whatsapp=test_user.whatsapp,
                ad_type='sell',
                admin_status='approved'
            ).limit(5).all()
            
            if len(sell_ads) >= 5:
                batch_id = str(uuid.uuid4())
                batch = Batch(batch_id=batch_id, created_at=datetime.utcnow())
                db.session.add(batch)
                
                for idx, ad in enumerate(sell_ads):
                    junction = BatchAd(batch_id=batch_id, ad_id=ad.ad_id, position=idx)
                    db.session.add(junction)
                    ad.batch_id = batch_id
                
                db.session.commit()
                print(f"  [OK] Batch kreye ak {len(sell_ads)} ADS")
            else:
                print(f"  [INFO] Pa ase ADS sell pou kreye batch (bezwen 5)")
        except Exception as e:
            print(f"  [ERR] Kreye batch: {e}")
            db.session.rollback()
        
        return True


if __name__ == '__main__':
    success = create_ads()
    if success:
        print("\n✅ ADS de test créées avec succès!")
        print("Connectez-vous avec:")
        print("  WhatsApp/Pseudo: +50912345678 ou testuser")
        print("  Mot de passe: 123456")
        print("\nPour voir les ADS:")
        print("  - Accueil: http://localhost:5000/")
        print("  - MarketPlace: http://localhost:5000/mache/")
        print("  - Admin: http://localhost:5000/admin/")
    else:
        print("\n❌ Erreur lors de la création des ADS")
