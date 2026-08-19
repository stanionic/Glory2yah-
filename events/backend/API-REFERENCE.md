# API — Module ÉVÉNEMENTS (Glory2YahPub)

Base : `/api/events`

Ce contrat est indépendant du framework. Adaptez-le en routes Next.js
(`/app/api/events/[slug]/route.js`), en contrôleurs Laravel, ou en
routes Rails — la logique SQL des migrations reste identique.

## Endpoints publics

### `GET /api/events/:slug`
Retourne les données complètes d'un événement publié (hero, leaders,
programme, FAQ, médias, résumé).
→ 404 si `status != 'published'`.

### `GET /api/events/:slug/stats`
Retourne les statistiques **anonymisées** (vue `event_public_stats`) :
```json
{
  "participants_count": 1240,
  "eglises_count": 86,
  "regions_represented": 10,
  "shares_count": 512
}
```
Aucune donnée personnelle. Jamais de liste nominative publique.

### `POST /api/events/:slug/participants`
Inscription individuelle. Body :
```json
{
  "full_name": "string (requis)",
  "phone": "string (requis)",
  "email": "string (optionnel)",
  "city": "string",
  "region": "string (nom du département)",
  "organization_name": "string",
  "role_label": "pasteur|responsable|membre|jeune|groupe_de_priere|organisation|autre",
  "participation_type": "individuelle|eglise|mission|organisation|ligue_de_pasteurs|groupe_de_priere",
  "consent_public_stats": false
}
```
- Validation stricte côté serveur (voir `src/validators.js`).
- Rate limit : 5 requêtes / IP / 10 min.
- Honeypot anti-spam (`website` field caché, doit rester vide).
→ `201 { "id": "uuid" }`

### `POST /api/events/:slug/organizations`
Inscription d'Église/organisation. Body : voir table `event_organizations`.
Statut initial : `pending`, à valider par un administrateur.
→ `201 { "id": "uuid", "status": "pending" }`

### `POST /api/events/:slug/shares`
Incrémente un compteur de partage (facultatif, purement analytique).
Body : `{ "channel": "whatsapp|facebook|messenger|x|telegram|link" }`
→ `204`

## Endpoints admin (authentification requise — réutiliser le système d'auth existant de Glory2YahPub)

Toutes les routes ci-dessous exigent le middleware d'auth admin déjà en place dans votre app.

| Méthode | Route | Description |
|---|---|---|
| PATCH | `/api/admin/events/:slug` | Modifier titre, description, dates, statuts |
| GET | `/api/admin/events/:slug/participants` | Liste paginée des participants |
| GET | `/api/admin/events/:slug/organizations` | Liste + validation des inscriptions d'Églises |
| PATCH | `/api/admin/events/:slug/organizations/:id` | Changer le statut (pending → confirmed/rejected) |
| POST/PATCH/DELETE | `/api/admin/events/:slug/coordinators` | Gérer les coordinateurs départementaux |
| POST/PATCH/DELETE | `/api/admin/events/:slug/news` | Publier des actualités |
| POST/PATCH/DELETE | `/api/admin/events/:slug/media` | Gérer photos/vidéos |
| POST/PATCH/DELETE | `/api/admin/events/:slug/faq` | Gérer la FAQ |
| PATCH | `/api/admin/events/:slug/program` | Modifier le programme |

## Créer un nouvel événement (sans toucher au code)

1. `INSERT INTO events (...) VALUES (...)` avec un nouveau `slug`.
2. La route front `/evenements/:slug` lit dynamiquement l'événement par son slug.
3. Ajouter leaders/programme/FAQ via les endpoints admin ci-dessus.
4. Passer `status` à `published` quand prêt.

Aucune modification du code applicatif n'est nécessaire pour ajouter un événement.
