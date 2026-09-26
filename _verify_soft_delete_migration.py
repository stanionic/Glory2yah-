"""Verify that the SOFT DELETE MIGRATION added deleted_at to existing tables."""
import sqlite3
import os

# Load the app (triggers SOFT DELETE MIGRATION at startup)
from app import create_app
app = create_app('development')

# Determine the development DB file
from app.config import DevelopmentConfig
db_uri = DevelopmentConfig.SQLALCHEMY_DATABASE_URI
print(f"DB URI: {db_uri}")

# Extract SQLite file path
if 'sqlite:///' in db_uri:
    db_file = db_uri.replace('sqlite:///', '')
    print(f"DB file: {db_file}")
    print(f"DB file exists: {os.path.exists(db_file)}")
    
    conn = sqlite3.connect(db_file)
    tables = ['users', 'ads', 'deliveries', 'cart_items', 'loan_products',
              'investment_products', 'gkach_transactions', 'messages']
    for t in tables:
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (t,)
        ).fetchone()
        if exists:
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({t})")]
            print(f"{t}: deleted_at={'deleted_at' in cols}")
        else:
            print(f"{t}: TABLE NOT FOUND")
    conn.close()
else:
    print("Not a SQLite DB — skipping file check")
