# MIGRATION SQLite → PostgreSQL sur RENDER

> À lire AVANT toute action. La donnée de PRODUCTION est sur le disque persistant
> Render (`/opt/render/project/src/instance/glory2yahpub_dev.db`), PAS forcément
> dans ta copie locale. Fais toujours une sauvegarde avant de migrer.

## 0. Prérequis (à faire une seule fois)

1. **Commiter + pousser** les nouveaux fichiers pour qu'ils existent sur Render :
   ```bash
   git add backup_db.py migrate_sqlite_to_postgres.py setup_postgres.py app/config.py render.yaml .env.example
   git commit -m "feat(db): PostgreSQL production config + SQLite->PG migration scripts"
   git push origin main     # Render re-déploie automatiquement
   ```
2. Attendre que le déploiement Render soit **vert** (Dashboard → Deploy).

> Le re-déploiement crée les tables vides sur le PostgreSQL managé
> (`glory2yahpub-db`) via `db.create_all()` au démarrage — c'est voulu.

---

## Chemin A — Depuis le SHELL RENDER (recommandé 🥇)

La source SQLite ET le `$DATABASE_URL` du Postgres sont tous les deux sur Render :
pas de DSN à manipuler, pas de mot de passe affiché.

1. Dashboard Render → service `glory2yahpub` → onglet **Shell**.
2. Sauvegarde d'abord la base source :
   ```bash
   python backup_db.py
   ```
3. Vérifier que la cible Postgres est joignable et prête :
   ```bash
   python setup_postgres.py --create-db
   ```
4. Aperçu de la migration (ne touche à rien) :
   ```bash
   python migrate_sqlite_to_postgres.py --target "$DATABASE_URL" --dry-run
   ```
5. Migration réelle :
   ```bash
   python migrate_sqlite_to_postgres.py --target "$DATABASE_URL"
   ```
   Codes exit : `0` ✅ tout copié · `2` ⚠️ lignes en échec (détails affichés) · `1` ❌ fatal.

6. Vérifier côté app : recharger le site (vides Redis : l'app invalide les caches
   au démarrage) et contrôler `/admin`.

---

## Chemin B — Depuis CE PC (il faut le DSN externe)

Le DSN externe est dans : Dashboard Render → **PostgreSQL** → `glory2yahpub-db`
→ **Connect** → `External Database URL`.

⚠️ La source locale (`instance/glory2yahpub_dev.db`) n'est la bonne source QUE si
elle est identique à la base de prod Render (copie téléchargée depuis le Shell).
Sinon tu écraserais la prod avec des données de dev.

```bash
# 1. MSSQL aucune donnée sur le Postgres cible (base neuve normalement)
# 2. Définir le DSN dans l'environnement (ne JAMAIS le commiter) :
#    (PowerShell)  $env:DATABASE_URL = "postgresql://user:pass@host:5432/db?sslmode=require"
python migrate_sqlite_to_postgres.py --target "$env:DATABASE_URL" --dry-run
python migrate_sqlite_to_postgres.py --target "$env:DATABASE_URL"
```

---

## ⛑️ Sécurité / Rollback

- **Sauvegarde** : `python backup_db.py` → copie horodatée dans `instance/backups/`
  (vérifiée : intégrité + comptes de lignes, garde les 10 dernières).
- **Idempotent** : re-exécuter le script est sans danger (`ON CONFLICT DO NOTHING`).
- **Rollback app** : la config permet de revenir à SQLite en retirant `DATABASE_URL`
  (mais la garde Production REFUSE SQLite → garde-le PostgreSQL une fois migré).
- Que faire localement maintenant :
  la Procédure complète est `setup_postgres.py` (booléen `--create-db`) puis
  `migrate_sqlite_to_postgres.py`.