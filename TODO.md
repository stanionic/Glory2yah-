# TODO - Correction du flux de checkout (négociation des frais de livraison)

## Objectif
Respecter la logique : le vendeur doit d'abord négocier les frais de livraison avec l'acheteur avant tout paiement.

## Étapes
- [x] Modifier `app/routes/cart.py` :
  - [x] Retirer la vérification de solde prématurée dans le POST `/checkout`
  - [x] Retirer l'appel à `GkachService.process_purchase()` (paiement immédiat)
  - [x] Créer uniquement les livraisons (`status='negotiating'`)
  - [x] Vider le panier après création des livraisons
- [x] Mettre à jour `templates/cart/checkout.html` (retirer la référence `data.donation`)
- [x] Vérifier `templates/delivery/detail.html` (déjà correct — négociation des frais de livraison)
- [x] Tester le flux complet (33/33 tests PASS)
