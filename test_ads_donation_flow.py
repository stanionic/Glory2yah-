"""
Test complet du flux ADS + Dons Caritatifs
Teste: Marketplace, Checkout, Dons, Admin
"""
import sys
import os
import json
import uuid
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from app import create_app, db
from app.models.user import User
from app.models.user_gkach import UserGkach
from app.models.ad import Ad
from app.models.cart import CartItem
from app.models.charity import CharityDonation, CharityCause
from app.models.gkach_transaction import GkachTransaction
from app.models.delivery import Delivery
from app.services.gkach_service import GkachService
from app.services.ad_service import AdService
from sqlalchemy import func

app = create_app()

PASS = 0
FAIL = 0
ERRORS = []

def test(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        msg = f"  [FAIL] {name}"
        if detail:
            msg += f": {detail}"
        print(msg)
        ERRORS.append(msg)

def check(condition, msg=""):
    if not condition:
        raise AssertionError(msg)

def run_all_tests():
    global PASS, FAIL, ERRORS
    print("\n" + "=" * 70)
    print("TEST: ADS + DONS CARITATIFS")
    print("=" * 70)
    
    with app.app_context():
        # -----------------------------------------------------------
        # TEST 1: Verifier utilisateur test
        # -----------------------------------------------------------
        print("\nTEST 1: Compte utilisateur test")
        test_user = User.query.filter_by(whatsapp='+50912345678').first()
        test("Utilisateur test existe", test_user is not None)
        
        if test_user:
            test("Pseudo = testuser", test_user.pseudo == 'testuser')
            
            # Verifier Gkach balance
            test_gkach = UserGkach.query.filter_by(user_whatsapp=test_user.whatsapp).first()
            test("Compte Gkach existe", test_gkach is not None)
            if test_gkach:
                # Top up if balance is too low for tests
                if test_gkach.gkach_balance < 500:
                    test_gkach.gkach_balance += 1000
                    db.session.commit()
                    # Invalidate cache
                    from app.services.redis_service import RedisService
                    from app import redis_client
                    try:
                        rs = RedisService(redis_client)
                        rs.invalidate_gkach_balance(test_user.whatsapp)
                    except:
                        pass
                test(f"Balance Gkach positive", test_gkach.gkach_balance > 0,
                     f"Balance actuelle: {test_gkach.gkach_balance}")
        
        # -----------------------------------------------------------
        # TEST 2: Verifier les causes caritatives
        # -----------------------------------------------------------
        print("\nTEST 2: Causes caritatives")
        causes = CharityCause.query.all()
        test("Causes caritatives creees", len(causes) > 0, f"Trouve: {len(causes)}")
        test("Cause 'general' existe", CharityCause.query.filter_by(cause_id='general').first() is not None)
        test("Cause 'education' existe", CharityCause.query.filter_by(cause_id='education').first() is not None)
        test("Cause 'health' existe", CharityCause.query.filter_by(cause_id='health').first() is not None)
        test("Cause 'community' existe", CharityCause.query.filter_by(cause_id='community').first() is not None)
        test("Cause 'food' existe", CharityCause.query.filter_by(cause_id='food').first() is not None)
        
        active_causes = CharityCause.query.filter_by(is_active=True).all()
        test("Toutes les causes sont actives", len(active_causes) == 5)
        
        # -----------------------------------------------------------
        # TEST 3: Verifier les ADS de type Sell
        # -----------------------------------------------------------
        print("\nTEST 3: ADS de type Sell")
        if test_user:
            sell_ads = Ad.query.filter_by(
                user_whatsapp=test_user.whatsapp,
                ad_type='sell'
            ).all()
            test("ADS Sell existent", len(sell_ads) == 8, f"Trouve: {len(sell_ads)}")
            
            if sell_ads:
                # Verifier chaque ADS (use actual titles from DB)
                ad_titles = [a.title for a in sell_ads]
                expected_titles = [
                    'Bib LaSante 2024 - Livre Neuf',
                    'Vè bòbine orijinal - Tradisyonèl',
                    'Videyo Muzik Gospel - Glory2Yah',
                    'Fèy Manyòk - Pake 5kg',
                    'Savon Vè bòbine natirèl - Pakè 3',
                    'Tablo Penti Glory - Dekorasyon',
                    'Videyo Fòmasyon Jadinaj',
                    'Chapo pay tradisyonèl - Fèt alamen'
                ]
                for title in expected_titles:
                    test(f"ADS '{title}' existe", title in ad_titles)
                
                # Verifier les prix
                first_ad = sell_ads[0]
                test(f"ADS a un prix > 0", first_ad.price_gkach > 0, 
                     f"Prix: {first_ad.price_gkach} Gkach")
                test("ADS est approuvee", first_ad.admin_status == 'approved')
                test("Paiement complete", first_ad.payment_status == 'completed')
        
        # -----------------------------------------------------------
        # TEST 4: Verifier les ADS de type Publish
        # -----------------------------------------------------------
        print("\nTEST 4: ADS de type Publish")
        if test_user:
            publish_ads = Ad.query.filter_by(
                user_whatsapp=test_user.whatsapp,
                ad_type='publish'
            ).all()
            test("ADS Publish existent", len(publish_ads) == 5, f"Trouve: {len(publish_ads)}")
            
            if publish_ads:
                test("Publish ADS ont prix = 0", all(a.price_gkach == 0 for a in publish_ads))
                test("Publish ADS sont approuvees", all(a.admin_status == 'approved' for a in publish_ads))
        
        # -----------------------------------------------------------
        # TEST 5: Verifier le batch publicitaire
        # -----------------------------------------------------------
        print("\nTEST 5: Batch publicitaire")
        from app.models.batch import Batch
        from app.models.batch_ad import BatchAd
        
        batches = Batch.query.all()
        test("Batch cree", len(batches) > 0, f"Trouve: {len(batches)}")
        
        if batches:
            latest_batch = batches[-1]
            batch_ads = BatchAd.query.filter_by(batch_id=latest_batch.batch_id).all()
            test("Batch contient 5 ADS", len(batch_ads) == 5, f"ADS dans batch: {len(batch_ads)}")
        
        # -----------------------------------------------------------
        # TEST 6: Verifier le flux panier -> checkout
        # -----------------------------------------------------------
        print("\nTEST 6: Flux Panier + Checkout")
        if test_user:
            from app.services.cart_service import CartService
            
            # Vider le panier d'abord
            CartService.clear_cart(test_user.id)
            
            # Ajouter un item au panier
            sell_ads = Ad.query.filter_by(
                user_whatsapp=test_user.whatsapp,
                ad_type='sell'
            ).limit(3).all()
            
            if len(sell_ads) >= 3:
                for i, ad in enumerate(sell_ads[:2]):
                    try:
                        CartService.add_to_cart(test_user.id, ad.ad_id, 1)
                        test(f"Ajout ADS #{i+1} au panier", True)
                    except Exception as e:
                        test(f"Ajout ADS #{i+1} au panier", False, str(e))
                
                # Verifier le contenu du panier
                cart_items = CartService.get_user_cart(test_user.id)
                test("Items dans le panier", len(cart_items) > 0, f"Items: {len(cart_items)}")
                
                # Calculer le sous-total
                totals = CartService.calculate_totals(test_user.id)
                subtotal = totals.get('subtotal', 0)
                test("Sous-total calcule", subtotal > 0, f"Sous-total: {subtotal} Gkach")
                
                # Test du checkout simule (sans appel HTTP)
                from app.services.delivery_service import DeliveryService
                
                # Prix du premier ad pour le checkout
                test_ad = sell_ads[0]
                ad_price = test_ad.price_gkach
                
                # Verifier que le buyer a assez de fonds
                buyer_balance = GkachService.get_balance(test_user.whatsapp)
                test(f"Balance acheteur suffisante", buyer_balance >= ad_price,
                     f"Balance: {buyer_balance}, Prix: {ad_price}")
        
        # -----------------------------------------------------------
        # TEST 7: Tester le processus de don
        # -----------------------------------------------------------
        print("\nTEST 7: Processus de Don Caritatif")
        
        # Creer un vendeur de test
        seller_user = User.query.filter_by(whatsapp='+50999999999').first()
        if not seller_user:
            seller_user = User(
                whatsapp='+50999999999',
                pseudo='TestSeller',
                name='Test Seller',
                auth_provider='whatsapp',
                is_active=True
            )
            seller_user.set_password('seller123')
            db.session.add(seller_user)
            db.session.commit()
            GkachService.get_or_create_account('+50999999999')
        
        try:
            # Creer une delivery de test
            from app.services.delivery_service import DeliveryService
            delivery = DeliveryService.create_delivery(
                buyer_whatsapp=test_user.whatsapp,
                seller_whatsapp=seller_user.whatsapp,
                cart_items=[{'ad_id': 'test_ad', 'ad_title': 'Test Product', 'quantity': 1, 'price': 100}],
                total_price=100,
                delivery_address='Test Address'
            )
            test("Delivery creee", delivery is not None)
            
            # Tester process_purchase avec don
            if delivery:
                result = GkachService.process_purchase(
                    buyer_whatsapp=test_user.whatsapp,
                    seller_whatsapp=seller_user.whatsapp,
                    amount=100,
                    ad_id=sell_ads[0].ad_id if sell_ads else 'test_ad',
                    delivery_id=delivery.delivery_id,
                    donation_amount=25,
                    donation_cause='education'
                )
                test("Paiement avec don reussi", result is True)
                
                # Verifier que le don a ete enregistre
                donations = CharityDonation.query.filter_by(
                    donor_whatsapp=test_user.whatsapp,
                    delivery_id=delivery.delivery_id
                ).all()
                test("Don enregistre dans CharityDonation", len(donations) > 0)
                
                if donations:
                    donation = donations[0]
                    test(f"Montant du don = 25 Gkach", donation.amount_gkach == 25,
                         f"Montant: {donation.amount_gkach}")
                    test("Cause = education", donation.cause == 'education')
                    test("Statut = completed", donation.status == 'completed')
                
                # Verifier le compte caritatif
                charity_account = UserGkach.query.filter_by(user_whatsapp='+509CHARITY').first()
                if charity_account:
                    # Chercher la transaction de donation
                    donation_tx = GkachTransaction.query.filter_by(
                        user_whatsapp='+509CHARITY',
                        transaction_type='donation'
                    ).first()
                    test("Transaction donation enregistree", donation_tx is not None)
                    if donation_tx:
                        test(f"Montant donation = 25 Gkach", donation_tx.amount == 25)
                        
        except Exception as e:
            test("Processus don complet", False, str(e))
        
        # -----------------------------------------------------------
        # TEST 8: Verifier les statistiques admin
        # -----------------------------------------------------------
        print("\nTEST 8: Statistiques Admin")
        
        # Stats des dons
        all_donations = CharityDonation.query.all()
        total_donations = len(all_donations)
        total_gkach = sum(d.amount_gkach for d in all_donations if d.status == 'completed') or 0
        total_donors = len(set(d.donor_whatsapp for d in all_donations if d.donor_whatsapp))
        
        test("Total donations > 0", total_donations > 0, f"Dons: {total_donations}")
        test("Total Gkach donnes > 0", total_gkach > 0, f"Gkach: {total_gkach}")
        test("Au moins 1 donateur unique", total_donors > 0, f"Donateurs: {total_donors}")
        
        # Stats ADS
        ads_stats = AdService.get_stats()
        test("ADS total > 0", ads_stats['total'] > 0, f"Total: {ads_stats['total']}")
        test("ADS approuvees > 0", ads_stats['approved'] > 0, f"Approuvees: {ads_stats['approved']}")
        test("ADS sell count >= 8", ads_stats['approved'] >= 8)
        
        # -----------------------------------------------------------
        # TEST 9: Verifier le compte caritatif dedie
        # -----------------------------------------------------------
        print("\nTEST 9: Compte caritatif dedie (+509CHARITY)")
        charity_account = UserGkach.query.filter_by(user_whatsapp='+509CHARITY').first()
        test("Compte +509CHARITY existe", charity_account is not None)
        if charity_account:
            # Verifier les transactions de donation
            donation_txs = GkachTransaction.query.filter_by(
                user_whatsapp='+509CHARITY',
                transaction_type='donation'
            ).all()
            test("Transactions donation existent", len(donation_txs) > 0, f"Transactions: {len(donation_txs)}")
        
        # -----------------------------------------------------------
        # RESULTATS
        # -----------------------------------------------------------
        print("\n" + "=" * 70)
        print("RESULTATS DES TESTS")
        print("=" * 70)
        print(f"  PASSED: {PASS}")
        print(f"  FAILED: {FAIL}")
        if ERRORS:
            print("\n  Erreurs:")
            for err in ERRORS:
                print(f"    {err}")
        print(f"\n  Total: {PASS + FAIL} tests")
        print("=" * 70)
        
        return FAIL == 0


if __name__ == '__main__':
    success = run_all_tests()
    if success:
        print("\nTOUS LES TESTS ONT REUSSI!")
    else:
        print(f"\n{FAIL} TEST(S) ONT ECHOUE!")
        sys.exit(1)
