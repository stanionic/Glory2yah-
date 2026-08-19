# Intégration dans Glory2YahPub — Module ÉVÉNEMENTS / SOS ALO LEGLIZ

## 1. Avant de coder (à faire vous-même ou avec votre équipe)
Comme convenu, ce scaffold est **framework-agnostic** côté SQL/logique, mais avant
de le brancher, vérifiez dans votre code existant :
- le framework backend réel (Express seul ? Next.js API routes ? autre ?)
- le système d'authentification admin déjà en place (à réutiliser, jamais dupliquer)
- le pool PostgreSQL existant, s'il y en a déjà un (`src/db.js` ne doit pas coexister
  avec un second pool)
- les conventions de nommage de vos autres tables/routes

## 2. Appliquer les migrations
```bash
psql $DATABASE_URL -f migrations/001_create_events_schema.sql
```
Ceci crée les tables, la vue de stats anonymisées, et insère l'événement
`sos-alo-legliz` en `status='draft'`.

## 3. Passer l'événement en ligne
```sql
UPDATE events SET status = 'published' WHERE slug = 'sos-alo-legliz';
```

## 4. Monter les routes
Voir `src/app.example.js`. En résumé :
```js
app.use('/api/events', require('./routes.events.public'));
app.use('/api/admin/events', requireAdminAuth, require('./routes.events.admin'));
```

## 5. Frontend
Servez `sos-alo-legliz.html` (déjà livré) sur la route `/evenements/sos-alo-legliz`,
en remplaçant les données statiques par des appels à `GET /api/events/sos-alo-legliz`
et en branchant le formulaire sur `POST /api/events/sos-alo-legliz/participants`
et `/organizations`. Architecture prévue pour ajouter d'autres événements via
`/evenements/:slug` sans dupliquer le code (voir point 6 du prompt original).

## 6. Dépendances à installer
```bash
npm install pg express-rate-limit
npm install --save-dev jest supertest
```

## 7. Variables d'environnement
Copier `.env.example` → `.env` et renseigner `DATABASE_URL`.

## 8. Tests
```bash
npx jest
```

## 9. Recommandations de sécurité (déjà appliquées dans le code fourni)
- Requêtes paramétrées partout (`$1, $2...`) → pas d'injection SQL.
- Validation stricte côté serveur (`src/validators.js`), même si le front valide déjà.
- Rate limiting sur les formulaires publics (5 requêtes / 10 min / IP).
- Honeypot anti-spam (champ `website` caché).
- IP jamais stockée en clair (hash SHA-256).
- Données personnelles jamais exposées via les endpoints publics — seule la vue
  `event_public_stats` (agrégée, anonyme) est publique.
- Coordonnées des coordinateurs départementaux : champ `is_public_contact`
  contrôle explicitement leur visibilité.
- **À ajouter par vous** selon votre stack : protection CSRF si vous utilisez
  des sessions cookies (non nécessaire si vous êtes en API token/JWT stateless),
  et HTTPS obligatoire en production.

## 10. Créer un futur événement
Aucun nouveau code requis :
1. `INSERT INTO events (...)` avec un nouveau `slug`.
2. Dupliquer/adapter le fichier HTML de landing page avec le nouveau slug,
   ou idéalement le rendre dynamique en tirant les données via
   `GET /api/events/:slug`.
3. Ajouter leaders, programme, FAQ via les routes admin.
4. `status = 'published'` quand prêt.

Cette architecture correspond au parcours demandé :
`/events`, `/events/sos-alo-legliz`, `/events/autre-evenement`, etc.
