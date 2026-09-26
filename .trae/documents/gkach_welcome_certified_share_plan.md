# Plan d'Implémentation — Gkach Welcome + Certification Vendeurs/Produits + Smart Sharing + Cashback 2% au Sharer + Analytics

## 1. Synthèse Audit Technique (§1 du Prompt)

### Architecture Globale de Glory2YahPub

| Couche | État actuel |
|---|---|
| **Flask Entry** | [app/\_\_init\_\_.py](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/app/__init__.py) : `create_app()` avec `db`, `migrate` (Flask-Migrate), `limiter` (Flask-Limiter), `redis_client` (Redis lazy + fallback None), `login_manager`, `csrf`. Pas de dossier `migrations/` local (configuré mais non initialisé dans le repo, upgrade via `db.create_all()` et colonnes manquantes rattrapées par `getattr` guard) |
| **Blueprints** | `main_bp`, `auth_bp`/auth, `marketplace_bp`/mache, `cart_bp`/cart, `delivery_bp`/delivery, `gkach_bp`/gkach, `admin_bp`/admin, `share_bp`/s, + `events/elearning/jere_biznis/...` conditionnels |
| **Models (SQLAlchemy)** | Dossier [app/models/](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/app/models/) — 20+ modèles. Voir matrice ci-dessous. |
| **Services** | [gkach_service.py](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/app/services/gkach_service.py) (ledger atomic+cache), [ad_service.py](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/app/services/ad_service.py), [redis_service.py](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/app/services/redis_service.py) (cache+rate+leaderboard+pubsub), [notification_service.py](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/app/services/notification_service.py) (liens WhatsApp uniquement — pas de DB notifications persistées ni push) |
| **Templates** | Base `extends "base.html"` + OG meta tags denses (défense 2 couches) dans [ad_detail.html](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/templates/ad_detail.html) / [share_shortlink.html](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/templates/share_shortlink.html). Design Mobile First → cartographie existante AliExpress (Royal Blue #1e3a8a / Gold #f59e0b / White). |
| **CSS/JS** | `static/css/g2y-app.css`, `static/css/gkach.css`. JS vanilla dans templates + `script.js`. |
| **Database** | SQLite par défaut en local, configurable Postgres `DATABASE_URL`. Contrainte CHECK `check_positive_balance` sur `user_gkach`, UNIQUE sur `user_whatsapp`. |
| **Auth** | Flask-Login, rate limit `@limiter` 10 register/h / 30 login/min, SECRET_KEY persistée instance/.flask_secret_key. CSRF global. |
| **Marketplace** | `/mache` → Blueprint `marketplace` filtrant `ad_type='sell' + admin_status='approved'`. Prix en `price_gkach` colonne `Ad`. Modèle Ad est aussi le modèle "Produit". |
| **Gkach (monnaie)** | Wallet `UserGkach` (clé `user_whatsapp`). Ledger `GkachTransaction` (type, old/new balance, meta_data JSON). Atomic `SELECT…FOR UPDATE` sur `add_balance/deduct_balance`. Cache Redis TTL 5 min. Types existants: credit/debit/purchase/sale/reward/refund/transfer_in_out/commission/donation/purchase_hold/admin_credit_debit + cashback (ajouté session précédente) + withdrawal (ajouté session précédente). |
| **Orders / Livraisons** | Modèle `Delivery` (status: negotiating → accepted → confirmed → awaiting_delivery → completed / cancelled) + `DeliveryItem`. Lié à `Ad.ad_id`. Appel `GkachService.process_purchase()` au moment du confirm payment. |
| **Payments** | Hors Gkach : purchase flow interne `Gkach` + `MonCash` (demande de recharge wallet → admin valide manuellement). |
| **Sharing / Récompenses** | 2 piliers existants : (a) shortlinks `/s/<ad_id>` — crawler-friendly OG, redirect JS humans vers `/ad/<ad_id>`, soft increment `share_count` anti-bot. (b) Batches `/s/b/<batch_id>?r=<referrer>` — tracking `batch_clicks` UNIQUE(referrer, clicker, batch), reward `10 Gk / 100 clics`. AUCUN share-link **product-level** avec referrer. |
| **Admin SEVIS** | `/admin` dashboard `admin.html`, `admin_manage_gkach.html`, `admin_edit_user.html`, `admin_audit.html`, etc. Actions POST bulk. `is_admin` boolean User. |
| **Notifications** | Service WhatsApp-link generation SEULEMENT. AUCUN modèle UserNotification persistent, AUCUN affichage in-app "cloche". |
| **Redis** | OUI, `strict=False` — `redis_client=None` si indispon. Utilisé: cache balances/ads, rate limit, compteurs, sessions, leaderboard, pubsub. Source de vérité TOUJOURS PostgreSQL/SQLite. |
| **Tests** | Fichiers `_sanity_*.py` ad-hoc locaux. AUCUN framework unittest/pytest configuré, AUCUN dossier tests/ dédié fonctionnel. |
| **Config** | [app/config.py](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/app/config.py) : Dev/Test/Prod/Staging. Toutes nouvelles constantes ajoutées dans `Config`. |
| **Sécurité** | CSRF global, rate-limit sur routes sensibles, HMAC device cookie `g2y_device` signé, validateurs `validate_whatsapp / validate_amount / sanitize_text`, SQLAlchemy paramétrisé, mot de passe hashé werkzeug. |

### 2. Matrice EXISTE / PARTIEL / MANQUANT / À AMÉLIORER / BUGUÉ

| Fonctionnalité demandée | État actuel | Observations audit |
|---|---|---|
| **§2 Gkach Welcome 50 Gk** | ❌ MANQUANT | Aucune logique dans [auth.py register()](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/app/routes/auth.py#L103-L159). AUCUN type `welcome_bonus` dans gkach_transactions. |
| **§3 Protection double bonus** | ❌ MANQUANT | Pas de colonne `welcome_bonus_granted_at` ni de contrainte d'unicité. |
| **§4 Séparation des Gkach Welcome** | ⚠️ PARTIEL | Solde unique `gkach_balance` (pas `welcome_balance` / `regular_balance`). Utiliser ledger + `meta_data.source` + champs sur `UserGkach` pour séparer sans casser les existants. |
| **§5 Utilisation limitée Welcome** | ❌ MANQUANT | `process_purchase()` n'a AUCUNE vérification de certification produit, aucune restriction source Welcome. |
| **§6 Priorité de débit Welcome → Regular** | ❌ MANQUANT | `deduct_balance` débite un compteur unique. |
| **§7 Produits certifiés** | ❌ MANQUANT | Modèle `Ad` n'a AUCUNE colonne `is_certified / certified_at / certified_by`. |
| **§8 Vendeurs certifiés** | ❌ MANQUANT | AUCUN modèle. `User.is_admin` seul existe. |
| **§9 Admin gestion vendeurs certifiés** | ❌ MANQUANT | `admin_manage_gkach.html` + `admin_edit_user.html` n'ont ni liste, ni filtre, ni action certification. |
| **§10 Certif produit indépendante vendeur** | ❌ MANQUANT | Colonnes manquantes. |
| **§11 Achat produit non certifié + Welcome** | ❌ MANQUANT | Vérification + message erreur créole à implémenter dans `process_purchase` ET dans UI ad_detail / cart / checkout. |
| **§12 Cashback 2% → SHARER** | 🔥 **BUGUÉ / CONFLIT** | Session précédente (commit antérieur) a implémenté `cashback=2% → ACHETEUR` dans `process_purchase()` — **contraire explicitement à §12**. Le cashback allait à la MAUVAISE personne. **À RE-CORRIGER : migrer vers le sharer referrer via attribution depuis share_token**. |
| **§13 Smart Social Sharing** | ⚠️ PARTIEL | Shortlink `/s/<ad_id>` existe, mais **SANS referrer** ni attribution share-level produit. Batches existent mais pour des groupes, pas pour un produit unique. |
| **§14 Pas de média dans le partage** | ✅ EXISTE | `share_shortlink.html` + OG meta server-side : utilisateurs cliquent lien vers G2Y, réseaux sociaux récupèrent la preview depuis les `<meta property=og:*>`. Rien à modifier. |
| **§15 Preview OG server-side** | ✅ EXISTE (fort) | 2 couches de défense Python + Jinja, og:image/video/url/type, og:video pour embed FB/WA, twitter:card complet. |
| **§16 Compatibilité réseaux** | ✅ EXISTE | UA-based crawler detection 30+ tokens, og + twitter + facebook OG. |
| **§17 Token unique non prévisible** | ❌ MANQUANT | Actuellement query string `?r=<whatsapp>` (numéro exposé, prévisible, falsifiable). Besoin token HMAC signé 128-bit. |
| **§18 Clic sur le lien tracking** | ⚠️ PARTIEL pour batches, ❌ MANQUANT pour produit | `/s/<short_id>` ne fait qu'increment `share_count` sans attribution persistente referrer→visiteur→produit. |
| **§19 Visiteur non connecté = attribution** | ❌ MANQUANT | AUCUN cookie/session `g2y_attribution` signé pour conserver sharer_id à travers navigation/connexion. |
| **§20 Relation sharer ↔ visitor ↔ produit** | ❌ MANQUANT | Aucun modèle `product_share` ni `share_attribution`. |
| **§21 Attribution survive login** | ❌ MANQUANT | Login handler ne rattache AUCUNE attribution session au compte connecté. |
| **§22 Règle d'attribution** | — (aucune) | On va documenter et appliquer **Last-Click-Windowed (Last Valid Referrer 30 jours)** : standard ecommerce, cohérent avec §12. |
| **§23 Anti auto-référence** | ⚠️ PARTIEL | `batch_clicks` ignore auto-clic. A généraliser aux product shares. |
| **§24 Statuts cashback PENDING/CONFIRMED/PAID/CANCELLED/REVERSED** | ❌ MANQUANT | Actuellement le cashback précédent va direct en `completed` sans life-cycle. |
| **§25 Montant éligible cashback (pas livraison/taxe)** | ❌ MANQUANT | Calcul sur `price_gkach` (pas `total_price`). À documenter. |
| **§26 Double cashback impossible** | ⚠️ PARTIEL | À renforcer : `UniqueConstraint(delivery_id, related_user, transaction_type IN (cashback_*))`. |
| **§27 Tracking interactions VIEW/LIKE/SHARE/CLICK/ADD_TO_CART/CHECKOUT/PURCHASE** | ⚠️ PARTIEL | `Ad.view_count / like_count / share_count` existent. Aucun `ad_events` table granulaire avec share_id/sharer_id/session_id/platform. |
| **§28-31 Analytics partageurs** | ❌ MANQUANT | Dashboard utilisateur "MES ANALYTICS" : AUCUNE page. |
| **§32 Analytics quasi temps réel** | ⚠️ PARTIEL | Redis + compteurs existent, aucun polling/pubsub UI dédié. |
| **§33 Redis non source de vérité financière** | ✅ EXISTE | Bonne hygiène actuelle. Conserver. |
| **§34 Dashboard SEVIS GKACH & REWARDS** | ❌ MANQUANT | Dashboard admin global n'a AUCUN bloc Welcome + Certification + Cashback stats. |
| **§35 Ledger financier** | ✅ EXISTE + extension | `GkachTransaction` + `meta_data`. Ajouter les nouveaux types `welcome_bonus / cashback_pending / cashback_credit / cashback_reversal / withdrawal_fee`. |
| **§36 Notifications** | ⚠️ PARTIEL | Service WhatsApp existe. MANQUE : Modèle notifications persisté + UI in-app (cloche). Pour MVP Welcome / Certification / Cashback V2 : on commence par flash messages + liens WhatsApp, on ajoute une table `user_notifications` sans casser le existant. |
| **§37 Mobile-first** | ✅ EXISTE | Design existant respecte. |
| **§38 Sécurité** | ✅ Base solide | Vérifications server-side nécessaires sur nouveaux endpoints. |
| **§39 Anti-fraude social** | ⚠️ PARTIEL | Rate limiter, UA, IP guards, HMAC device → étendre aux product_share + events. |
| **§40 Performance** | — | Utiliser Redis `HINCRBY` analytics + bulk flush DB. Index sur colonnes FK + status + dates. |
| **§41 Migrations** | ⚠️ PARTIEL | `Migrate()` chargé mais AUCUN dossier `migrations/` versionné. Fallback `db.create_all()` OK, colonnes nouvelles ont default. On fournit un script Python `_migrate_cert_welcome_share.py` idempotent (ALTER TABLE) qui couvre SQLite+PostgreSQL sans Alembic. |
| **§42 Tests unitaires** | ⚠️ PARTIEL | On écrit un script e2e `_sanity_welcertshare.py` SQLite-mémoire qui couvre : bonus unique, double clic, certif produit/vendeur, debit priorisé, cashback sharer, anti-auto-ref, token forgeable, attribution last-click 30d. |

---

## 3. Décisions d'Architecture Preserve-First

### 3.1 Gestion colonnes sans Alembic
Flask-Migrate est instancié mais **0 migrations versionnées**. Pour éviter de casser les bases existantes Render/SQLite :
- **Stratégie** : colonnes nouvelles ont TOUTES une valeur par défaut (0, None, false).
- **Script idempotent** `scripts/migrate_welcertshare.py` (à exécuter 1× après deploy) qui fait `ALTER TABLE ADD COLUMN IF NOT EXISTS` + `CREATE TABLE IF NOT EXISTS` + `CREATE UNIQUE INDEX IF NOT EXISTS`. Compatible SQLite (PRAGMA table_info) ET PostgreSQL (information_schema). Compatible `db.create_all()` pour bases fraîches — classes modèles déclarent les colonnes normalement.

### 3.2 Séparation Welcome vs Regular Gkach
Choix ledger-centric (sans colonnes séparées `welcome_balance / regular_balance` — qui casseraient 100+ références à `user_gkach.gkach_balance` dans UI/templates/services existants) :
- Ajout colonnes `UserGkach.welcome_balance_remaining INTEGER DEFAULT 0` et `total_welcome_received INTEGER DEFAULT 0`.
- Règle : `welcome_balance_remaining <= total_welcome_received`.
- `deduct_balance_with_priority(certified_product=True)` débite **Welcome d'abord** (max welcome_remaining), puis Regular. Si produit non certifié : Welcome refusé, débit Regular seulement.
- `get_balance()` retourne TOUJOURS `gkach_balance` identique (somme Welcome + Regular) — compatibilité parfaite UI existante.
- Chaque transaction a `meta_data['welcome_portion']` et `meta_data['regular_portion']` pour la traçabilité §6.

### 3.3 Cashback §12 — Correction critique
**SUPPRIMER** la ligne qui donne `cashback → acheteur` (fausse implémentation session précédente). Nouveau flux:
1. `product_shares.tracking_token` signé non prévisible (8-12 chars base64url).
2. Click `/s/<ad_id>?ref=<token>` → résout `sharer_id`.
3. Cookie signé `g2y_ref_{ad_id}=<sharer_whatsapp:token:created_at_epoch:hmac>` (HttpOnly, 30 jours, SameSite=Lax).
4. Au login/register → migrate cookie → `share_attributions` table.
5. `process_purchase(delivery_id, ad_id, buyer_whatsapp, amount_htg_or_gk)` → lit l'attribution Last-Valid-Referrer (30j).
6. `cashback_amount = floor(amount_eligible * GKACH_CASHBACK_PCT / 100)` → **vers SHARER** comme `cashback_pending`.
7. Lorsque Delivery passe `confirmed` (statut confirmé) → `cashback_pending → cashback_credit` (confirmé puis crédit direct sur wallet avec PAID). Delivery cancelled → `cashback_reversal`.
8. Auto-reference guard: `sharer_whatsapp == buyer_whatsapp` → cashback annulé (type REVERSED).
9. Contrainte UNIQUE `(delivery_id, related_user, transaction_type IN (cashback_pending,cashback_credit))` — empêche §26 double cashback.

### 3.4 Modèles NOUVEAUX vs EXTEND existants (préserve-first : 0 suppression)

**NOUVEAUX MODÈLES (zéro impact sur existant):**
- `SellerCertification` (§8) — `id, seller_whatsapp FK users.whatsapp, status (PENDING/CERTIFIED/SUSPENDED/REVOKED), certified_by, certified_at, suspended_at, revoked_at, notes TEXT, created_at` + `SellerCertificationHistory` (log changement de statut).
- `ProductShare` (§13/17) — `share_id UUID, ad_id FK ads.ad_id, sharer_whatsapp, tracking_token UNIQUE, platform, created_at, clicks_count INTEGER DEFAULT 0` + Index `(tracking_token)`.
- `ShareAttribution` (§20/21) — `id, visitor_device_id HMAC, visitor_whatsapp NULLABLE, ad_id FK, share_id FK, sharer_whatsapp, attached_at, expires_at, session_id` + Unique (visitor_whatsapp, ad_id) — last click gagne (upsert + update `attached_at`).
- `AdEvent` (§27) — `id, event_type (VIEW/LIKE/SHARE/CLICK/ADD_TO_CART/CHECKOUT/PURCHASE), ad_id, user_whatsapp NULLABLE, share_id NULLABLE, sharer_whatsapp NULLABLE, session_id, platform, visitor_device_id, ip_hash, metadata JSON, created_at` + Index (ad_id, event_type, created_at).
- `UserNotification` (§36 MVP) — `id, user_whatsapp, category, title, body_html, is_read, data_json, created_at`.

**EXTENSIONS MODÈLES EXISTANTS:**
- `Ad` (§7/10) : + `is_certified BOOLEAN DEFAULT FALSE, certified_at DATETIME, certified_by VARCHAR(120), certification_notes TEXT`.
- `UserGkach` (§2-4-6) : + `welcome_balance_remaining INTEGER DEFAULT 0, total_welcome_received INTEGER DEFAULT 0, welcome_bonus_granted_at DATETIME`. Unique implicite via whatsapp PK + guard server-side atomic.
- `Delivery` (§12/24) : + `cashback_status VARCHAR(20), cashback_amount INTEGER DEFAULT 0, referral_share_id FK, referral_sharer_whatsapp VARCHAR(20)`.
- `GkachTransaction` : nouveau type autorisé enum string `welcome_bonus, cashback_pending, cashback_credit, cashback_reversal, referral_bonus` — aucun schéma à casser, c'est une string free.

### 3.5 Règle d'attribution (§22) — Documentée et appliquée
> **Last Valid Referrer (LVR) avec fenêtre de 30 jours.**
> Si un visiteur clique sur le lien de User A (jour 0), puis 25j après sur le lien de User B, puis achète → **User B reçoit le cashback**.
> Exception: auto-référencement sharer==buyer → **0 cashback + flag REVERSED** (anti §23).

### 3.6 Analytics quasi temps réel (§32)
Pile Redis `HINCRBY` analytique key `analytics:user:<whatsapp>:<YYYY-MM>` avec champs `views/likes/shares/clicks/add_to_cart/checkouts/purchases/revenue_gk/cashback_gk`. À chaque `AdEvent` écrit, on incrémente Redis d'abord, puis write DB en bulk batch (flush 30s). UI dashboard "Mes Analytics" fait **polling léger 15s fetch `/gkach/api/analytics`** (pas WebSocket — pas d'infra Socket.IO sur le wallet). Suffisant quasi-temps-réel, compatible Render.

---

## 4. Fichiers à Modifier / Créer (ordre de dépendance)

### 🔧 Groupe A — Config + Modèles + Migration (zéro UI, base)

1. **[app/config.py](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/app/config.py)** — + constantes :
   ```
   GKACH_WELCOME_BONUS = 50
   GKACH_WELCOME_MIN_SOLD = 500
   GKACH_CASHBACK_PCT = 2            # (ré-utilisé, sens changé : → SHARER)
   GKACH_CASHBACK_WINDOW_DAYS = 30
   GKACH_CASHBACK_ONLY_CERTIFIED_PRODUCTS = False
   SMART_SHARE_TOKEN_LENGTH = 10
   ANALYTICS_FLUSH_INTERVAL_SEC = 30
   ```

2. **[app/models/user_gkach.py](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/app/models/user_gkach.py)** — + colonnes welcome & contraintes ; méthodes `deduct_prioritized(amount, requires_certified_product=False)`.

3. **[app/models/ad.py](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/app/models/ad.py)** — + `is_certified, certified_at, certified_by, certification_notes` ; Badge helper `is_certified_label`.

4. **NOUVEAU [app/models/certifications.py](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/app/models/certifications.py)** — `SellerCertification` + `SellerCertificationHistory`.

5. **NOUVEAU [app/models/shares.py](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/app/models/shares.py)** — `ProductShare`, `ShareAttribution`, `AdEvent`.

6. **NOUVEAU [app/models/notifications.py](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/app/models/notifications.py)** — `UserNotification`.

7. **[app/models/__init__.py](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/app/models/__init__.py)** — importer tous nouveaux modèles pour que `db.create_all()` les prenne.

8. **NOUVEAU [scripts/migrate_welcertshare.py](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/scripts/migrate_welcertshare.py)** — script idempotent ALTER TABLE compat SQLite + PostgreSQL.

---

### ⚙️ Groupe B — Couche Services (logique métier, sans UI)

9. **[app/services/gkach_service.py](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/app/services/gkach_service.py)** — MODIFICATIONS IMPORTANTES:
   - ⚠️ **SUPPRIMER** la section `cashback amount > 0 → crédit à buyer` de `process_purchase()` (§12 override).
   - Nouveau `grant_welcome_bonus(new_user_whatsapp, [idempotency_key])` — atomic `SELECT…FOR UPDATE`, vérifie `welcome_bonus_granted_at IS NULL`, crée transaction type `welcome_bonus`, incrémente welcome_balance_remaining.
   - `deduct_balance_with_priority(user_wa, amount, requires_certified=False, meta={})` → retour `{amount, welcome_portion, regular_portion, ok, message_creole}`.
   - `restrict_welcome_withdrawal()` — guard pour `request_withdrawal()` (interdit l'utilisation welcome pour cashout §5).
   - `restrict_welcome_transfer()` — guard pour `transfer()` §5.
   - Nouveau `create_cashback_pending(delivery_id, ad_id, amount_eligible, sharer_wa, buyer_wa, share_id)` → type `cashback_pending`, UNIQUE guard delivery+sharer.
   - `confirm_or_reverse_cashback(delivery_id, action=confirm|reverse)`.
   - Nouveau `get_analytics_summary(user_wa, range=30d)` — agrège AdEvent + gkach transactions.

10. **NOUVEAU [app/services/share_service.py](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/app/services/share_service.py)** — :
    - `create_product_share(ad_id, sharer_wa, platform='whatsapp')` → génère token non prévisible secrets.token_urlsafe, persist ProductShare, retourne URL `/s/<ad_id>?ref=<token>`.
    - `resolve_tracking_token(token)` → share record, vérifie expir, anti-tamper.
    - `record_attribution(share, visitor_wa_nullable, visitor_device, session_id)` → last-click upsert ShareAttribution, expire 30j.
    - `find_referrer_for_purchase(buyer_wa, visitor_device, ad_id, delivery_id)` → Last Valid Referrer 30j, exclue auto-ref.
    - Anti-fraude helpers: `ip_hash()`, `rate_limit_share()`, `block_self_share()`.

11. **NOUVEAU [app/services/analytics_service.py](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/app/services/analytics_service.py)** — Redis HINCRBY async counters, bulk flush → DB AdEvent, agrégats par produit/plateforme/plage temporelle.

12. **[app/services/notification_service.py](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/app/services/notification_service.py)** — + `persist_user_notification()` ; templates messages créole pour Welcome 50Gk, Cashback reçu, Vendeur certifié.

---

### 🛣️ Groupe C — Routes Flask (intégrations)

13. **[app/routes/auth.py](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/app/routes/auth.py)** — `register()` : après `db.session.add(user); flush;` → `GkachService.grant_welcome_bonus(whatsapp, idempotency_key=user.whatsapp + ":" + user.created_at_str)` → `flash("🎁 Félicitations! 50 Gkach Welcome...", "success")`. Dans `login()` : post succès, migrer les ShareAttribution depuis cookie signé `g2y_attributions` → DB avec `visitor_whatsapp=current_user.whatsapp`.

14. **[app/routes/share.py](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/app/routes/share.py)** — :
    - `single_ad(short_id)` : si `?ref=<token>` présent, `ShareService.resolve_tracking_token` + `record_attribution` + cookie signé 30 jours `g2y_ref` + `g2y_attributions` (batch). Incrément ProductShare.clicks_count. Continue OG meta + redirect existant.
    - **NOUVELLE** `@share_bp.route('/p/create', methods=['POST']) @login_required` → `ShareService.create_product_share(form.ad_id, form.platform)` → JSON `{share_url, tracking_token}`.

15. **[app/routes/delivery.py](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/app/routes/delivery.py)** — au moment de `process_purchase()` (statut confirmed) :
    - `sharer = ShareService.find_referrer_for_purchase(buyer, ad)` (inclut auto-reference guard).
    - `amount_eligible = Ad.price_gkach (pas delivery_cost)`.
    - `cb_id = GkachService.create_cashback_pending(delivery, ad, amount_eligible, sharer, buyer)`.
    - Quand Delivery → confirmed (post OTP validation vendeur+acheteur) → `GkachService.confirm_or_reverse_cashback(delivery_id, 'confirm')`.
    - Si Delivery cancelled → reverse.

16. **[app/routes/marketplace.py](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/app/routes/marketplace.py)** — + paramètre query `?certified=1` filter, expose `ad.is_certified` champ au template product card.

17. **[app/routes/cart.py](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/app/routes/cart.py)** — checkout: avertissement créole si panier mixte certifié/non + Welcome insuffisant.

18. **[app/routes/gkach.py](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/app/routes/gkach.py)** — 3 nouvelles routes:
    - `@gkach_bp.route('/analytics')` → page `gkach/analytics.html` (dashboard MES ANALYTICS §28).
    - `@gkach_bp.route('/api/analytics')` → JSON par défaut 30j, params ?range=7/30/90/365/custom.
    - Guards `request_withdrawal()` bloque portion Welcome (minimum 500 regular).
    - Guards `transfer()` bloque portion Welcome.

19. **[app/routes/admin.py](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/app/routes/admin.py)** — NOUVELLES actions + dashboard:
    - Admin dashboard principal: section `GKACH & REWARDS` (§34).
    - `manage_sellers_certification()` — search/filtre/filter par statut/certifier/suspendre/revoquer/historique/note.
    - `manage_products_certification(ad_id)` — certifier/décertifier produit indépendamment vendeur.
    - Vue `pending_withdrawals` déjà existante → intégrer.
    - `admin_manage_gkach`: card Welcome Bonus distributed / utilisé / restant.

---

### 🎨 Groupe D — Templates / CSS / JS (UI)

20. **[templates/ad_detail.html](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/templates/ad_detail.html)** — :
    - Badge `✓ PRODUIT CERTIFIÉ GLORY2YAHPUB` (royal blue #1e3a8a + gold #f59e0b background gradient + ombre douce).
    - Badge vendeur certifié (icône bouclier doré) si SellerCert.status=CERTIFIED.
    - Bloc Smart Share Links (icônes WhatsApp/FB/FB-Messenger/Telegram/X/Copier lien) — chaque bouton → `ShareService.create_product_share(ad_id, platform, sharer=current_user)` via POST fetch, puis ouvre `wa.me/?text=...` avec **LIEN G2Y SEULEMENT (pas média)** (respect §14).
    - OG meta tag mis à jour: badge certifié mentionné dans `og:description` ("✓ Certifié Glory2YahPub — 500 HTG").

21. **NOUVEAU [templates/gkach/analytics.html](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/templates/gkach/analytics.html)** — Dashboard "MES ANALYTICS":
    - Filtres période (Aujourd'hui / 7j / 30j / 3mois / Année / Perso).
    - 8 KPI cards: Views / Likes / Shares / Clicks / Add to Cart / Purchases / Sales HTG / Cashback Gk.
    - Section analytics PAR PRODUIT (tableau produit → KPI).
    - Section analytics PAR PLATEFORME (WhatsApp/FB/Telegram... → ventes).
    - Polling 15s léger.

22. **[templates/gkach/wallet.html](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/templates/gkach/wallet.html)** — :
    - Petite mention sous le solde "🎁 Welcome: XX Gkach disponibles (seulement produits certifiés)".
    - Bouton 💡 Accès "Mes Analytics" ajouté dans balance-actions.
    - Historique: nouveaux types `welcome_bonus / cashback_pending / cashback_credit / cashback_reversal` avec icônes + texte créole.

23. **NOUVEAU [templates/admin_sellers.html](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/templates/admin_sellers.html)** — Gestion vendeurs certifiés §9 (recherche, filtre, actions, historique).

24. **[templates/admin.html](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/templates/admin.html)** — Dashboard principal: section `GKACH & REWARDS` 4 cartes Welcome + 4 Certification + 4 Cashback + 4 Social Analytics (§34).

25. **[templates/marketplace/index.html](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/templates/marketplace/index.html)** — Cards produits: badge `✓ CERTIFIÉ` sur produit certifié, filtre UI "Montrer seulement certifiés".

---

### ✅ Groupe E — OG Meta + Base Templates (§15/16)

26. **[templates/base.html](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/templates/base.html)** — Vérifier/bloc `{% block og_meta %}` disponible pour override.

27. **[templates/ad_detail.html](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/templates/ad_detail.html)** — Déjà robuste. Ajout du badge dans `og:description` + `product:price:amount HTG` (via taux GKACH_TO_HTG_RATE). Twitter card `summary_large_image`.

28. **[templates/share_shortlink.html](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/templates/share_shortlink.html)** — Mise à jour identique pour badge certifié (crawler verra le badge).

---

### 🧪 Groupe F — Sécurité / Anti-fraude (§38/39)

29. **HMAC cookie `g2y_attributions`** — même pattern existant `_sign_device_id()` pour éviter la falsification.
30. **Rate limit** sur `/s/p/create` (POST 5/minute/user), sur `/s/<ad_id>?ref=` (60/min/IP hérité).
31. **Anti auto-share** sharer==buyer : cashback reversed + meta_data.flag=auto_reference.
32. **Tokens tracking** non prévisibles: `secrets.token_urlsafe(SMART_SHARE_TOKEN_LENGTH)` — jamais `user_id` en clair dans URL.
33. **Validations côté serveur**: cashback calcul server-side SEULEMENT (jamais trust frontend amount). Certification produit read-only côté client — validée DB dans `process_purchase`.

---

### 🧪 Groupe G — Tests + Validation (§42)

34. **NOUVEAU [_sanity_welcertshare.py](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/_sanity_welcertshare.py)** — SQLite in-memory + `db.create_all()`, scénarios:
    - Test 1: Register user → welcome_balance=50, gkach_balance=50, type welcome_bonus logged.
    - Test 2: Double appel `grant_welcome_bonus` → guard OK (montant toujours 50).
    - Test 3: Requete concurrente via threads → atomic SELECT FOR UPDATE, 0 doublon.
    - Test 4: Produit certifié vs non certifié — si non certifié welcome refusé, Regular utilisé.
    - Test 5: Mix Welcome=50 Regular=100 Achat certifié=80 → welcome_portion=50 regular=30.
    - Test 6: Vendeur certifié PENDING → CERTIFIED → SUSPENDED → historisé.
    - Test 7: Product share → token non prévisible, résolution OK, forge d'un token rejeté.
    - Test 8: Click → attribution cookie 30j, login → attribution migrée.
    - Test 9: Last click (User A puis User B) → B gagne cashback.
    - Test 10: Auto-reference → cashback reversed + balance intacte.
    - Test 11: Transfer & Withdrawal utilisent Regular seulement — Welcome refusé.
    - Test 12: Delivery cancelled → cashback reversal.
    - Test 13: Double cashback tentative → UNIQUE guard OK.
35. **Validation compilation** : `py_compile app/**/*.py`.

---

## 5. Risques et Mitigations

| Risque | Impact | Mitigation |
|---|---|---|
| ⚠️ **Conflit §12 — cashback acheteur récent** | Cashback va à la MAUVAISE personne (acheteur au lieu de sharer). | Dans le plan, Groupe B étape 9 **supprime explicitement** la section cashback→acheteur. Migration data: une tâche admin manuelle (ou script) pourra lister les cashback acheteur existants type `cashback` → convertir en regular credit administrateur (non réversible sans risque, mais aucun achat réel n'a été fait sur cette session). |
| Colonnes nouvelles + bases existantes | ALTER TABLE non appliqué → KeyError. | Tous `getattr(col, default)` dans le code, script migration idempotent, `_safe_ad_to_dict()` déjà utilisé dans marketplace. |
| Redis down | Compteurs analytics perte | Source de vérité DB AdEvent + ShareAttribution. Redis = accélérateur. Fallback direct DB. |
| Produit certifié vendeur non certifié | Ambiguïté §10. | **Règle explicite**: Certification produit est **indépendante**. UI affiche les 2 badges séparément. Cashback Sharer fonctionne sur tous produits (certifiés ET non, configurable). Welcome Gkach = uniquement produits **avec certification produit=true**. |
| Forge token / cookie attribution | Fraude cashback. | HMAC SHA256 signé SECRET_KEY + `compare_digest` (pattern `_sign_device_id` réutilisé). |
| Auto-partage frauduleux | User génère lien, clique, achète lui-même. | Guard `sharer_wa == buyer_wa → no cashback` (flag + status REVERSED). IP guard + device guard renforcé. |
| Cashback life-cycle incohérent | Cashback crédité avant delivery confirmed. | `cashback_pending` d'abord, confirmation au changement Delivery.status=confirmed. |
| Performance 10k visites/jour | Événements DB gonflés. | `AnalyticsService` utilise Redis HINCRBY, bulk flush toutes les 30s vers DB. |
| Migration Alembic inexistante | Perte contrôle schema. | **On NE crée PAS de migrations Alembic** (risque casser). On fournit un script `scripts/migrate_welcertshare.py` idempotent. `db.create_all()` couvre fresh install. |

---

## 6. Ordre d'Exécution Recommandé (après approbation)

```
A1. config.py constantes
A2. Modèles (user_gkach extend → ad extend → certifications → shares → notifications → __init__)
A3. script migration idempotent
B9. gkach_service: grant_welcome + deduct_priority + retire cashback acheteur + cashback life-cycle
B10.share_service (tokens, attribution, find_referrer)
B11.analytics_service
B12.notification_service persist
C13.auth register welcome + login migrate attribution cookie→DB
C14.share.py shortlink ref-param + POST /p/create
C15.delivery hook cashback at confirm/cancel
C16.marketplace certified filter
C17.cart guards certifié/welcome
C18.gkach analytics UI + API + guards transfer/withdraw welcome forbidden
C19.admin sellers_cert + products_cert + dashboard GKACH & REWARDS
D20.ad_detail badges + share widget
D21.analytics page
D22.wallet mention welcome
D23.admin_sellers template
D24.admin dashboard section
D25.marketplace card badges
E26-E28. OG meta updates
G34._sanity_welcertshare.py e2e
G35.py_compile all
```

---

## 7. Validation Finale (avant de considérer done)
- [ ] Tous scénarios `_sanity_welcertshare.py` passent (0 erreurs, exit 0).
- [ ] `py_compile app/**/*.py` 0 erreurs.
- [ ] Migration idempotent script s'exécute 2× sans erreur (reproductibilité).
- [ ] UI login → `flash Welcome 50Gk` s'affiche, compteur welcome=50.
- [ ] UI produit certifié → badge bleu/or apparaît.
- [ ] Produit non certifié + solde welcome=50 regular=0 → checkout refusé avec message créole.
- [ ] Produit certifié + welcome=50 regular=100 + prix=80 → welcome=50, regular=30.
- [ ] Share User A → User B achète → User A reçoit cashback_pending → confirmed=PAID, User B 0.
- [ ] Same user share & buy → cashback REVERSED (0 effective).
- [ ] Transfer 50 impossible depuis solde 100% welcome (50), message erreur.
