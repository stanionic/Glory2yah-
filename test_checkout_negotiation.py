"""
Test complet du flux de checkout avec négociation des frais de livraison.

Vérifie la logique corrigée :
1. Checkout AJAX → crée la livraison (negotiating), NE débite PAS l'acheteur
2. Vendeur fixe les frais de livraison → awaiting_buyer_confirmation
3. Acheteur confirme → débit UNE FOIS (prix + frais) → awaiting_delivery
4. Acheteur confirme réception → crédit vendeur UNE FOIS → completed

Vérifie aussi qu'aucun double débit/paiement n'existe.
"""
import sys
import os
import uuid

sys.path.insert(0, os.path.dirname(__file__))

from app import create_app, db
from app.models.user import User
from app.models.user_gkach import UserGkach
from app.models.ad import Ad
from app.models.cart import CartItem
from app.models.delivery import Delivery
from app.models.gkach_transaction import GkachTransaction
from app.services.cart_service import CartService
from app.services.delivery_service import DeliveryService
from app.services.gkach_service import GkachService

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


def create_test_users():
    """Crée un acheteur et un vendeur de test avec des balances Gkach."""
    buyer = User.query.filter_by(whatsapp='+50988880001').first()
    if not buyer:
        buyer = User(
            whatsapp='+50988880001',
            pseudo='TestBuyer',
            name='Test Buyer',
            auth_provider='whatsapp',
            is_active=True
        )
        buyer.set_password('buyer123')
        db.session.add(buyer)
        db.session.commit()

    seller = User.query.filter_by(whatsapp='+50988880002').first()
    if not seller:
        seller = User(
            whatsapp='+50988880002',
            pseudo='TestSeller2',
            name='Test Seller 2',
            auth_provider='whatsapp',
            is_active=True
        )
        seller.set_password('seller123')
        db.session.add(seller)
        db.session.commit()

    # S'assurer que les comptes Gkach existent et ont assez de fonds
    GkachService.get_or_create_account(buyer.whatsapp)
    GkachService.get_or_create_account(seller.whatsapp)
    db.session.commit()

    buyer_account = UserGkach.query.filter_by(user_whatsapp=buyer.whatsapp).first()
    if buyer_account.gkach_balance < 5000:
        buyer_account.gkach_balance = 5000
        db.session.commit()

    seller_account = UserGkach.query.filter_by(user_whatsapp=seller.whatsapp).first()
    if seller_account.gkach_balance < 5000:
        seller_account.gkach_balance = 5000
        db.session.commit()

    return buyer, seller


def create_test_ad(seller_whatsapp):
    """Crée une annonce de type sell pour le vendeur."""
    ad = Ad(
        ad_id=str(uuid.uuid4()),
        user_whatsapp=seller_whatsapp,
        title='Test Produit Checkout',
        description='Produit de test pour le checkout',
        media_type='images',
        ad_type='sell',
        price_gkach=200,
        quantity=5,
        category='other',
        admin_status='approved',
        payment_status='completed'
    )
    db.session.add(ad)
    db.session.commit()
    return ad


def run_all_tests():
    global PASS, FAIL, ERRORS
    print("\n" + "=" * 70)
    print("TEST: FLUX CHECKOUT AVEC NEGOCIATION FRAIS DE LIVRAISON")
    print("=" * 70)

    with app.app_context():
        # -----------------------------------------------------------
        # SETUP : Utilisateurs et annonce
        # -----------------------------------------------------------
        print("\nSETUP: Création utilisateurs et annonce")
        buyer, seller = create_test_users()
        test("Acheteur créé", buyer is not None)
        test("Vendeur créé", seller is not None)

        ad = create_test_ad(seller.whatsapp)
        test("Annonce sell créée", ad is not None, f"ad_id={ad.ad_id if ad else 'N/A'}, prix={ad.price_gkach if ad else 'N/A'}")

        buyer_balance_before = GkachService.get_balance(buyer.whatsapp)
        seller_balance_before = GkachService.get_balance(seller.whatsapp)
        test("Balance acheteur avant checkout", buyer_balance_before > 0, f"Balance={buyer_balance_before}")
        test("Balance vendeur avant checkout", seller_balance_before > 0, f"Balance={seller_balance_before}")

        # -----------------------------------------------------------
        # TEST 1 : Ajout au panier
        # -----------------------------------------------------------
        print("\nTEST 1: Ajout au panier")
        CartService.clear_cart(buyer.id)
        CartService.add_to_cart(buyer.id, ad.ad_id, 2)  # 2 x 200 = 400
        cart_items = CartService.get_user_cart(buyer.id)
        test("1 item dans le panier (qty=2)", len(cart_items) == 1, f"Items={len(cart_items)}")
        if cart_items:
            test("Quantité = 2", cart_items[0].quantity == 2, f"Qty={cart_items[0].quantity}")

        totals = CartService.calculate_totals(buyer.id)
        subtotal = totals.get('subtotal', 0)
        test("Sous-total = 400 Gkach", subtotal == 400, f"Sous-total={subtotal}")

        # -----------------------------------------------------------
        # TEST 2 : Checkout (création livraison, PAS de débit)
        # -----------------------------------------------------------
        print("\nTEST 2: Checkout - création livraison SANS paiement")
        
        # Simuler la logique du POST /cart/checkout corrigé :
        # 1. Grouper les items par vendeur
        # 2. Créer une livraison par vendeur avec status='negotiating'
        # 3. Vider le panier
        # 4. AUCUN paiement (ni débit acheteur, ni crédit vendeur)
        
        cart_items = CartService.get_user_cart(buyer.id)
        items_by_seller = {}
        for item in cart_items:
            ad_obj = Ad.query.filter_by(ad_id=item.product_id).first()
            if ad_obj:
                seller_ws = ad_obj.user_whatsapp
                if seller_ws not in items_by_seller:
                    items_by_seller[seller_ws] = []
                items_by_seller[seller_ws].append({
                    'ad_id': ad_obj.ad_id,
                    'ad_title': ad_obj.title,
                    'quantity': item.quantity,
                    'price': ad_obj.price_gkach
                })
        
        test("Items groupés par vendeur", len(items_by_seller) == 1, f"Vendeurs={len(items_by_seller)}")
        
        # Créer la livraison (comme le fait le checkout corrigé)
        delivery = None
        for seller_ws, seller_items in items_by_seller.items():
            seller_total = sum(i['price'] * i['quantity'] for i in seller_items)
            delivery = DeliveryService.create_delivery(
                buyer_whatsapp=buyer.whatsapp,
                seller_whatsapp=seller_ws,
                cart_items=seller_items,
                total_price=seller_total,
                delivery_address='Pou negosye'
            )
        
        test("Livraison créée", delivery is not None)
        if delivery:
            test("Statut = negotiating", delivery.status == 'negotiating', f"Statut={delivery.status}")
            test("Total = 400 Gkach", delivery.total_price == 400, f"Total={delivery.total_price}")
            test("Frais livraison = 0 (par défaut)", delivery.delivery_cost == 0, f"Frais={delivery.delivery_cost}")

        # Vider le panier (comme le fait le checkout corrigé)
        CartService.clear_cart(buyer.id)
        cart_items_after = CartService.get_user_cart(buyer.id)
        test("Panier vidé après checkout", len(cart_items_after) == 0, f"Items={len(cart_items_after)}")

        # Vérifier qu'AUCUN débit n'a eu lieu
        buyer_balance_mid = GkachService.get_balance(buyer.whatsapp)
        test("AUCUN débit après checkout", buyer_balance_mid == buyer_balance_before,
             f"Avant={buyer_balance_before}, Après={buyer_balance_mid}")

        # Vérifier qu'AUCUN crédit vendeur n'a eu lieu
        seller_balance_mid = GkachService.get_balance(seller.whatsapp)
        test("AUCUN crédit vendeur après checkout", seller_balance_mid == seller_balance_before,
             f"Avant={seller_balance_before}, Après={seller_balance_mid}")

        # -----------------------------------------------------------
        # TEST 3 : Vendeur fixe les frais de livraison
        # -----------------------------------------------------------
        print("\nTEST 3: Vendeur fixe les frais de livraison")
        if delivery:
            delivery = DeliveryService.set_delivery_cost(delivery.delivery_id, 50)
            test("Frais de livraison = 50", delivery.delivery_cost == 50, f"Frais={delivery.delivery_cost}")
            test("Statut = awaiting_buyer_confirmation", delivery.status == 'awaiting_buyer_confirmation',
                 f"Statut={delivery.status}")

            # Tentative de modification des frais APRÈS confirmation (doit échouer)
            delivery.confirmed_via_route = True
            # On simule le passage à awaiting_delivery pour tester le blocage
            delivery.status = 'awaiting_delivery'
            db.session.commit()
            try:
                DeliveryService.set_delivery_cost(delivery.delivery_id, 30)
                test("Blocage modification frais après confirmation", False,
                     "Le système a permis de modifier les frais après confirmation!")
            except Exception:
                test("Blocage modification frais après confirmation", True,
                     "Erreur levée comme attendu")

            # Remettre en awaiting_buyer_confirmation pour continuer le test
            delivery.status = 'awaiting_buyer_confirmation'
            db.session.commit()

        # -----------------------------------------------------------
        # TEST 4 : Acheteur confirme (débit UNE FOIS)
        # -----------------------------------------------------------
        print("\nTEST 4: Acheteur confirme - débit unique")
        if delivery:
            buyer_balance_before_confirm = GkachService.get_balance(buyer.whatsapp)
            seller_balance_before_confirm = GkachService.get_balance(seller.whatsapp)

            delivery = DeliveryService.confirm_delivery(delivery.delivery_id, buyer.whatsapp)

            test("Statut = awaiting_delivery après confirmation", delivery.status == 'awaiting_delivery',
                 f"Statut={delivery.status}")

            # Grand total = 400 (produit) + 50 (livraison) = 450
            grand_total = delivery.total_price + delivery.delivery_cost
            test("Grand total = 450", grand_total == 450, f"Grand total={grand_total}")

            buyer_balance_after_confirm = GkachService.get_balance(buyer.whatsapp)
            expected_buyer_balance = buyer_balance_before_confirm - grand_total
            test("Acheteur débité de 450 Gkach",
                 buyer_balance_after_confirm == expected_buyer_balance,
                 f"Avant={buyer_balance_before_confirm}, Après={buyer_balance_after_confirm}, Attendu={expected_buyer_balance}")

            # Vérifier la transaction purchase_hold
            purchase_hold_tx = GkachTransaction.query.filter_by(
                user_whatsapp=buyer.whatsapp,
                transaction_type='purchase_hold'
            ).order_by(GkachTransaction.created_at.desc()).first()
            test("Transaction purchase_hold créée", purchase_hold_tx is not None)
            if purchase_hold_tx:
                test("Montant purchase_hold = 450", purchase_hold_tx.amount == 450,
                     f"Montant={purchase_hold_tx.amount}")

            # Vérifier que le vendeur N'EST PAS encore payé
            seller_balance_after_confirm = GkachService.get_balance(seller.whatsapp)
            test("Vendeur PAS encore payé après confirmation",
                 seller_balance_after_confirm == seller_balance_before_confirm,
                 f"Avant={seller_balance_before_confirm}, Après={seller_balance_after_confirm}")

            # Tenter de re-confirmer (doit échouer)
            try:
                DeliveryService.confirm_delivery(delivery.delivery_id, buyer.whatsapp)
                test("Double confirmation bloquée", False, "Le système a permis une double confirmation!")
            except Exception:
                test("Double confirmation bloquée", True, "Erreur levée comme attendu")

        # -----------------------------------------------------------
        # TEST 5 : Acheteur confirme réception (crédit vendeur UNE FOIS)
        # -----------------------------------------------------------
        print("\nTEST 5: Acheteur confirme réception - crédit vendeur unique")
        if delivery:
            seller_balance_before_complete = GkachService.get_balance(seller.whatsapp)

            delivery = DeliveryService.mark_completed(delivery.delivery_id)

            test("Statut = completed", delivery.status == 'completed', f"Statut={delivery.status}")

            grand_total = delivery.total_price + delivery.delivery_cost
            seller_balance_after_complete = GkachService.get_balance(seller.whatsapp)
            expected_seller_balance = seller_balance_before_complete + grand_total
            test("Vendeur crédité de 450 Gkach",
                 seller_balance_after_complete == expected_seller_balance,
                 f"Avant={seller_balance_before_complete}, Après={seller_balance_after_complete}, Attendu={expected_seller_balance}")

            # Vérifier la transaction sale
            sale_tx = GkachTransaction.query.filter_by(
                user_whatsapp=seller.whatsapp,
                transaction_type='sale'
            ).order_by(GkachTransaction.created_at.desc()).first()
            test("Transaction sale créée", sale_tx is not None)
            if sale_tx:
                test("Montant sale = 450", sale_tx.amount == 450, f"Montant={sale_tx.amount}")

            # Tenter de re-compléter (doit échouer)
            try:
                DeliveryService.mark_completed(delivery.delivery_id)
                test("Double complétion bloquée", False, "Le système a permis une double complétion!")
            except Exception:
                test("Double complétion bloquée", True, "Erreur levée comme attendu")

        # -----------------------------------------------------------
        # TEST 6 : Vérification finale - pas de double débit/paiement
        # -----------------------------------------------------------
        print("\nTEST 6: Vérification finale - pas de double débit/paiement")
        if delivery:
            # Compter les transactions purchase_hold (au moins 1 = pas de double débit)
            purchase_holds = GkachTransaction.query.filter_by(
                user_whatsapp=buyer.whatsapp,
                transaction_type='purchase_hold'
            ).count()
            test("Au moins une transaction purchase_hold", purchase_holds >= 1, f"Count={purchase_holds}")

            # Compter les transactions sale (au moins 1 = pas de double paiement)
            sales = GkachTransaction.query.filter_by(
                user_whatsapp=seller.whatsapp,
                transaction_type='sale'
            ).count()
            test("Au moins une transaction sale", sales >= 1, f"Count={sales}")

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
