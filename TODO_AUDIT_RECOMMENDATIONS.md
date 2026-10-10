# TODO - Recommandations d'audit Glory2YahPub

Ce plan reprend les risques constatés pendant l'audit général. Traiter les sections dans l'ordre; ne pas marquer une tâche terminée sans son critère de validation.

## P0 - Secrets et accès

- [ ] Révoquer le GitHub PAT exposé et en créer un nouveau avec les permissions minimales nécessaires.
- [ ] Renouveler `SECRET_KEY`, le mot de passe admin et la clé CallMeBot partagés; mettre les nouvelles valeurs dans les stockages privés locaux/Render, jamais dans Git, les logs ou les tickets.
- [ ] Vérifier que `.env` reste ignoré et que l'historique Git ne contient aucun secret; si un secret y figure, révoquer même après suppression du fichier.
- [ ] Retirer les identifiants de démonstration de la page de connexion en production et empêcher la création de comptes de démonstration en production.
- [ ] Supprimer les valeurs de repli de credentials admin des configurations non-développement; exiger une configuration explicite en staging/production.

**Critère de clôture :** les anciens secrets sont révoqués, aucune valeur active n'est suivie par Git, et les connexions admin/démonstration sont vérifiées en production.

## P1 - Parcours d'achat et fichiers sensibles

- [ ] Ajouter un test de route qui vérifie le POST valide avec CSRF et le comportement des POST avec token manquant/invalide.
- [ ] Valider côté serveur le type réel et la taille du document GKach; ne pas se fier à `accept` ou à l'extension fournie par le client.
- [ ] Stocker les preuves MonCash/NatCash hors du répertoire statique et les servir uniquement aux administrateurs autorisés.
- [ ] Ajouter une limite de débit au POST public `/achte_gkach` et une limite de fréquence/coût au déclenchement des alertes admin.

**Critère de clôture :** dépôt valide accepté, dépôt invalide/trop volumineux refusé, preuve inaccessible publiquement, comportements CSRF manquant/invalide couverts par tests et soumissions répétées limitées.

## P1 - Temps réel et base de données en production

- [ ] Fournir Redis à la production et définir `REDIS_URL` afin que Socket.IO partage l'état entre les workers.
- [ ] Remplacer le worker Gunicorn synchrone par une configuration Socket.IO officiellement compatible; documenter l'affinité de session si nécessaire.
- [ ] Ajouter un test d'intégration à deux clients pour partage média, annotations et synchronisation de vue sous le même déploiement.
- [ ] Activer `DB_ENFORCE_POSTGRES_PRODUCTION=1` sur Render pour empêcher un démarrage silencieux sur SQLite si `DATABASE_URL` manque.
- [ ] Tester un déploiement à froid avec la base PostgreSQL et Redis indisponibles, et vérifier que l'application échoue clairement plutôt que de recevoir des écritures sur une base de repli.

**Critère de clôture :** deux clients sur des workers différents reçoivent les événements, et aucune instance de production ne peut démarrer sur SQLite par inadvertance.

## P2 - Tests et automatisation

- [ ] Corriger l'assertion invalide dans `tests/test_admin_security.py` afin qu'elle vérifie réellement l'absence de credentials par défaut.
- [ ] Ajouter pytest aux dépendances de développement et documenter une commande de test reproductible.
- [ ] Ajouter une CI qui installe les dépendances, exécute les tests ciblés et bloque les régressions de sécurité/checkout.
- [ ] Ajouter des tests pour les uploads GKach, les alertes de tous les flux d'approbation et les événements Socket.IO multi-clients.
- [ ] Séparer les scripts de diagnostic/fixtures locaux des tests maintenus; supprimer les identifiants de démonstration et données sensibles de leurs sorties.

**Critère de clôture :** les tests passent sur une installation propre et la CI bloque un échec de test ou de syntaxe.

## P2 - Documentation et maintenance

- [ ] Corriger le README: remplacer `python run.py` par le lanceur réellement présent (`python simple_start.py`) et indiquer les prérequis de production.
- [ ] Documenter les variables Render requises, notamment `CALLMEBOT_APIKEY`, `REDIS_URL`, `DATABASE_URL`, `SECRET_KEY` et `ADMIN_PASSWORD`, sans valeur secrète d'exemple réutilisable.
- [ ] Décomposer progressivement `app/__init__.py` et `app/routes/main.py` en modules ciblés, avec tests autour des contrats déplacés.
- [ ] Définir une politique de mise à jour des dépendances épinglées et lancer un audit de vulnérabilités de dépendances à chaque release.

**Critère de clôture :** une nouvelle personne peut installer, démarrer, configurer et tester l'application à partir de la documentation seule.
