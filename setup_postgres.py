"""
Setup PostgreSQL Database for Glory2YahPub
This script will:
1. Install psycopg2-binary
2. Create the database
3. Import ads from images
"""
import sys
import os
import subprocess

print("=" * 60)
print("GLORY2YAHPUB - POSTGRESQL SETUP")
print("=" * 60)
print()

# Step 1: Install psycopg2
print("[1/4] Installing PostgreSQL driver...")
try:
    subprocess.run([sys.executable, "-m", "pip", "install", "psycopg2-binary"], 
                   check=True, capture_output=True)
    print("  [OK] psycopg2-binary installed")
except Exception as e:
    print(f"  [ERROR] Failed to install: {e}")
    print("\nManual install: pip install psycopg2-binary")
    sys.exit(1)

# Step 2: Test PostgreSQL connection
print("\n[2/4] Testing PostgreSQL connection...")
try:
    import psycopg2
    from dotenv import load_dotenv
    load_dotenv()
    
    db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/glory2yahpub')
    
    # Parse connection string
    if db_url.startswith('postgresql://'):
        parts = db_url.replace('postgresql://', '').split('@')
        user_pass = parts[0].split(':')
        host_db = parts[1].split('/')
        
        user = user_pass[0]
        password = user_pass[1] if len(user_pass) > 1 else ''
        host_port = host_db[0].split(':')
        host = host_port[0]
        port = host_port[1] if len(host_port) > 1 else '5432'
        dbname = host_db[1] if len(host_db) > 1 else 'glory2yahpub'
        
        print(f"  Connecting to: {host}:{port}/{dbname}")
        
        # Try to connect to postgres database first
        try:
            conn = psycopg2.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database='postgres'
            )
            conn.autocommit = True
            cursor = conn.cursor()
            
            # Check if database exists
            cursor.execute(f"SELECT 1 FROM pg_database WHERE datname='{dbname}'")
            exists = cursor.fetchone()
            
            if not exists:
                print(f"  Creating database: {dbname}")
                cursor.execute(f"CREATE DATABASE {dbname}")
                print(f"  [OK] Database created")
            else:
                print(f"  [OK] Database exists")
            
            cursor.close()
            conn.close()
            
        except psycopg2.OperationalError as e:
            print(f"  [ERROR] Cannot connect to PostgreSQL: {e}")
            print("\n  Make sure PostgreSQL is running:")
            print("    - Windows: Check Services for 'postgresql'")
            print("    - Or install: https://www.postgresql.org/download/")
            sys.exit(1)
            
    print("  [OK] PostgreSQL connection successful")
    
except ImportError:
    print("  [ERROR] psycopg2 not installed")
    sys.exit(1)
except Exception as e:
    print(f"  [ERROR] {e}")
    sys.exit(1)

# Step 3: Create tables
print("\n[3/4] Creating database tables...")
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from app import create_app, db
    
    app = create_app()
    with app.app_context():
        db.create_all()
        print("  [OK] Tables created")
        
except Exception as e:
    print(f"  [ERROR] {e}")
    sys.exit(1)

# Step 4: Import images
print("\n[4/4] Importing images as ads...")
try:
    exec(open('import_images.py').read())
    print("  [OK] Images imported")
except Exception as e:
    print(f"  [WARNING] Could not import images: {e}")
    print("  Run manually: python import_images.py")

print("\n" + "=" * 60)
print("POSTGRESQL SETUP COMPLETE!")
print("=" * 60)
print("\nDatabase URL:", os.getenv('DATABASE_URL'))
print("\nYou can now run: python run.py")
print("=" * 60)
