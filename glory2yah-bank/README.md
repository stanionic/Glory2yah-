# Glory2Yah Bank — Plateforme bancaire numérique sur GKach

Implémentation de référence (starter kit fonctionnel) du blueprint architectural de **Glory2Yah Bank**, une banque numérique construite **exclusivement au-dessus de GKach**, le Core Banking & Payment Engine de l'écosystème Glory2Yah.

> ⚠️ **Portée de ce code** : ceci est un scaffold d'architecture fonctionnel (microservices réels, API REST complètes, logique métier exécutable) destiné à démarrer le développement et à valider l'architecture. Le stockage utilise des structures **en mémoire** pour rester exécutable sans dépendances externes. Le schéma PostgreSQL complet de production est fourni dans `shared/sql/schema.sql` — le brancher est l'étape suivante avant tout déploiement réel. La sécurité (JWT, MFA, KYC/AML, chiffrement) est esquissée avec des points d'intégration clairs, à durcir avant mise en production.

## Règle d'architecture fondamentale

**GKach est l'unique système qui déplace de l'argent.** Aucun microservice Glory2Yah Bank n'écrit un solde ou un mouvement financier directement — tout passe par le client `shared/gkachClient.js` (copié dans chaque service), qui appelle les APIs GKach (`/wallet/*`, `/payment/*`).

## Structure du projet

```
glory2yah-bank/
├── gkach-core/                 # Core Banking & Payment Engine (wallets, ledger, paiements)
├── api-gateway/                # Point d'entrée unique : JWT, RBAC, rate limiting, routage
├── services/
│   ├── accounts/                # Comptes bancaires (personnel/entreprise/église/ONG/institution)
│   ├── savings/                 # Épargne libre/bloquée/programmée + intérêts
│   ├── investments/              # Plans Bronze/Silver/Gold/Platinum
│   ├── loans/                    # Pipeline complet de prêt
│   ├── crowdlending/             # Marketplace de financement participatif
│   ├── credit-score/             # Moteur IA : scoring, risque, fraude, prévision de défaut
│   ├── admin/                    # Taux, plans, utilisateurs, dashboard, reporting
│   └── notification/             # Email / SMS / Push / WhatsApp / in-app
├── shared/
│   ├── gkachClient.js            # Client HTTP partagé vers GKach
│   └── sql/schema.sql            # Schéma PostgreSQL complet de production
├── docker-compose.yml
└── scripts/dev-all.js            # Lance tous les services en local en une commande
```

## Démarrage rapide

### Option A — Docker Compose (recommandé)

```bash
docker compose up --build
```

Tous les services démarrent et sont accessibles via l'API Gateway sur `http://localhost:8080`.

### Option B — Local avec Node.js (>=20)

```bash
npm install          # installe toutes les dépendances (workspaces npm)
npm run dev           # lance les 10 services en parallèle via concurrently
```

## Ports par défaut

| Service | Port |
|---|---|
| API Gateway (point d'entrée public) | 8080 |
| GKach Core | 4000 |
| Accounts | 4100 |
| Savings | 4200 |
| Investments | 4300 |
| Loans | 4400 |
| Crowdlending | 4500 |
| AI Engine (credit-score) | 4600 |
| Admin & Reporting | 4700 |
| Notification | 4800 |

## Exemple de parcours complet (via l'API Gateway)

```bash
# 1. Obtenir un token JWT de démo
TOKEN=$(curl -s -X POST http://localhost:8080/auth/login \
  -H "Content-Type: application/json" \
  -d '{"user_id":"user-001","role":"client"}' | jq -r .token)

# 2. Créer un compte bancaire (crée aussi le wallet GKach associé)
curl -s -X POST http://localhost:8080/accounts \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"user_id":"user-001","account_type":"personnel","currency":"USD"}'

# Récupérer wallet_id depuis la réponse ci-dessus, puis :

# 3. Déposer des fonds (transite par GKach)
curl -s -X POST http://localhost:8080/wallet/deposit \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"wallet_id":"<WALLET_ID>","amount":1000,"method":"mobile_money"}'

# 4. Souscrire à un plan d'investissement Gold
curl -s -X POST http://localhost:8080/investment/create \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"user_id":"user-001","wallet_id":"<WALLET_ID>","plan_id":"gold","amount":1500}'

# 5. Demander un prêt personnel
curl -s -X POST http://localhost:8080/loan/apply \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"user_id":"user-001","wallet_id":"<WALLET_ID>","type":"personnel","amount":2000,"term_months":12}'

# 6. Approuver le prêt (nécessite le rôle admin — obtenir un token admin via /auth/login avec role=admin)
curl -s -X POST http://localhost:8080/loan/<LOAN_ID>/approve \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"admin_id":"admin-001"}'
```

## Passage en production — feuille de route technique

1. **Base de données** : remplacer le stockage en mémoire par PostgreSQL en utilisant `shared/sql/schema.sql` (un schéma/service, pattern "Database per Service").
2. **Bus d'événements** : remplacer `gkach-core/src/events.js` par un vrai cluster Kafka avec topics dédiés (`wallet.*`, `loan.*`, `escrow.*`) et consumer groups par microservice.
3. **Sécurité** : ajouter MFA (OTP), rotation des refresh tokens, chiffrement AES-256 au repos, intégration Vault pour les secrets, WAF devant l'API Gateway.
4. **KYC/AML** : brancher un fournisseur de vérification d'identité (pièce + liveness) et des listes de sanctions (PEP/OFAC) dans le service Accounts.
5. **IA** : remplacer le moteur de scoring à base de règles (`services/credit-score`) par des modèles entraînés (XGBoost / réseaux de neurones) exposés via une API Python FastAPI dédiée.
6. **Observabilité** : ajouter Prometheus/Grafana, ELK, et un tracing distribué (OpenTelemetry) sur chaque service.
7. **CI/CD** : pipelines GitHub Actions + déploiement GitOps (ArgoCD) sur Kubernetes, avec stratégie blue-green pour Loans/Investments.
8. **Frontend** : ce dépôt ne contient que le backend ; construire les apps Web (Next.js), Android (Kotlin) et iOS (Swift) consommant l'API Gateway.

## Référence complète

Pour la vision produit, les diagrammes d'architecture détaillés, le détail des flux métier et la roadmap complète, voir le document `Glory2Yah_Bank_Blueprint.md` fourni précédemment.
