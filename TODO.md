# TODO - Appliquer les priorités du rapport d'audit

## Priorité A : Index manquants (Phase 1 - Critique)
- [ ] 1. Auditer les index existants sur tous les modèles
- [ ] 2. Ajouter les index manquants (Delivery, GkachTransaction, Message, CartItem, etc.)
- [ ] 3. Vérifier la syntaxe

## Priorité B : Soft deletes (Phase 3 - Moyenne)
- [ ] 4. Ajouter `deleted_at` à BaseModel
- [ ] 5. Ajouter méthode `active()` dans BaseModel
- [ ] 6. Ajouter `deleted_at` aux modèles principaux (Ad, Delivery, CartItem, Message, GkachTransaction)
- [ ] 7. Vérifier la syntaxe

## Priorité C : Normalisation Delivery.cart_items (Phase 2)
- [ ] 8. Créer junction table `delivery_items`
- [ ] 9. Mettre à jour DeliveryService pour utiliser la junction table
- [ ] 10. Vérifier la syntaxe

## Tests
- [ ] 11. Lancer le serveur et vérifier que tout fonctionne
- [ ] 12. Commit et push
