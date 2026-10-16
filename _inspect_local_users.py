"""Read-only inspection of the local SQLite dev DB: who can log in?"""
import os
import sqlite3
import sys

DB = os.path.join("instance", "glory2yahpub_dev.db")
if not os.path.isfile(DB):
    print(f"NO DB at {DB}")
    sys.exit(0)

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
cur = con.cursor()

# columns of users
cols = [r["name"] for r in cur.execute("PRAGMA table_info(users)").fetchall()]
print("users columns:", cols)

total = cur.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
print(f"\nTOTAL users: {total}")

rows = cur.execute(
    "SELECT id, pseudo, whatsapp, is_admin, is_active, "
    "(password_hash IS NOT NULL AND password_hash != '') has_pw "
    "FROM users ORDER BY id"
).fetchall()
print(f"{'id':>4} {'pseudo':<18} {'whatsapp':<16} adm act has_pw")
for r in rows:
    print(f"{r['id']:>4} {str(r['pseudo']):<18} {str(r['whatsapp']):<16} "
          f"{r['is_admin']!s:<3} {r['is_active']!s:<3} {r['has_pw']}")

# other tables row counts (what content exists locally)
print("\n--- row counts per table ---")
tbls = [r["name"] for r in cur.execute(
    "SELECT name FROM sqlite_master WHERE type='table' "
    "AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()]
for t in tbls:
    try:
        c = cur.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        if c:
            print(f"  {t:<32} {c}")
    except Exception as e:
        print(f"  {t:<32} ERR {e}")

con.close()
