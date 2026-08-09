"""
Setup PostgreSQL Database for Glory2YahPub (idempotent, safe).

What it does:
  1. Reads DATABASE_URL (env or .env) and normalizes it:
        postgres://...  ->  postgresql://...   (Render legacy scheme)
  2. Verifies connectivity and, with --create-db, creates the database if it
     does not exist yet (requires CREATEDB privileges).
  3. Creates all tables via db.create_all() inside the app context
     (the idempotent startup migration patches inside create_app() also run).
  4. Optional: imports legacy images as ads if import_images.py exists.

Usage:
  python setup_postgres.py            # existing database only
  python setup_postgres.py --create-db  # also create the database if missing

The password is NEVER printed; only host/database/user are shown.
"""
import argparse
import os
import sys

from dotenv import load_dotenv
from sqlalchemy.engine import make_url

load_dotenv()


def normalize_url(url):
    """Render legacy postgres:// -> postgresql:// (SQLAlchemy 1.4+)."""
    if not url:
        return url
    url = url.strip()
    if url.startswith('postgres://'):
        url = 'postgresql://' + url[len('postgres://'):]
    return url


def ensure_database(dsn):
    """Connect to the maintenance `postgres` DB and CREATE DATABASE if missing.

    Uses parameterized identifiers (double-quote escaping) — no string
    interpolation into SQL except the safely-quoted database name.
    Returns True if the database was created, False if it already existed.
    """
    url = make_url(dsn)
    dbname = url.database
    if not dbname:
        print('  [ERROR] The connection string has no database name: postgresql://.../DBNAME')
        sys.exit(1)

    try:
        import psycopg2
    except ImportError:
        print('  [ERROR] psycopg2 is not installed. Run: pip install psycopg2-binary')
        sys.exit(1)

    try:
        conn = psycopg2.connect(
            host=url.host,
            port=url.port or 5432,
            user=url.username,
            password=url.password or '',
            database='postgres',
            connect_timeout=10,
        )
    except Exception as e:
        print(f'  [WARNING] Could not connect to the maintenance "postgres" DB: {e}')
        print('           The database is assumed to already exist — continuing.')
        return False

    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT 1 FROM pg_database WHERE datname = %s', (dbname,))
            if cur.fetchone():
                print(f'  [OK] database already exists: {dbname}')
                return False
            quoted = '"' + dbname.replace('"', '""') + '"'
            cur.execute('CREATE DATABASE {0}'.format(quoted))
            print(f'  [OK] database created: {dbname}')
            return True
    except Exception as e:
        print(f'  [ERROR] CREATE DATABASE failed: {e}')
        print('          (You need CREATEDB privileges — or create it manually.')
        sys.exit(1)
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description='Prepare the PostgreSQL database for Glory2YahPub.'
    )
    parser.add_argument(
        '--create-db',
        action='store_true',
        help='Create the database if it does not exist (needs CREATEDB privileges).',
    )
    args = parser.parse_args()

    print('=' * 60)
    print('GLORY2YAHPUB - POSTGRESQL SETUP')
    print('=' * 60)

    raw = os.getenv('DATABASE_URL') or os.getenv('DEV_DATABASE_URL')
    if not raw:
        print('[ERROR] DATABASE_URL is not set. Set it in .env or the shell.')
        sys.exit(1)

    dsn = normalize_url(raw)
    if not dsn.startswith('postgresql://'):
        print(f'[ERROR] Expected a PostgreSQL DSN (postgresql://...), got something else.')
        sys.exit(1)

    # Credential-safe summary (never print the password).
    safe = make_url(dsn)
    print(f'  Host:     {safe.host}:{safe.port or 5432}')
    print(f'  Database: {safe.database}')
    print(f'  User:     {safe.username}')

    if args.create_db:
        print('\n[1/4] Ensuring the database exists...')
        ensure_database(dsn)
    else:
        print('\n[1/4] Skipping DB creation (pass --create-db to create it if missing).')

    print('\n[2/4] Creating tables (db.create_all) + running startup patches...')
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from app import create_app, db
        app = create_app()
        with app.app_context():
            db.create_all()
            print('  [OK] Tables created')
    except Exception as e:
        print(f'  [ERROR] {e}')
        sys.exit(1)

    print('\n[3/4] Optional: import legacy images as ads...')
    importer = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'import_images.py')
    if os.path.isfile(importer):
        try:
            with open(importer, encoding='utf-8') as f:
                exec(f.read())
            print('  [OK] Images imported')
        except Exception as e:
            print(f'  [WARNING] Images import failed (optional step): {e}')
    else:
        print('  [SKIP] import_images.py not found — legacy import skipped.')

    print('\n[4/4] Verifying connection...')
    try:
        with app.app_context():
            db.session.execute(db.text('SELECT 1'))
            print('  [OK] Database reachable: SELECT 1 -> 1')
    except Exception as e:
        print(f'  [WARNING] Post-creation verification failed: {e}')

    print('\n' + '=' * 60)
    print('POSTGRESQL SETUP COMPLETE')
    print('=' * 60)
    print('Start the app with: python run.py  (or your usual entrypoint)')


if __name__ == '__main__':
    main()