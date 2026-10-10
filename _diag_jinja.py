"""Diag template syntax error ad_detail.html"""
import os, sys, tempfile
os.environ.setdefault('TESTING','True')
os.environ.setdefault('DATABASE_URL','sqlite:///:memory:')
tmpdir = tempfile.mkdtemp()
os.environ.setdefault('SESSION_FILE_DIR',tmpdir)
os.environ.setdefault('UPLOAD_FOLDER',tmpdir)
os.environ.setdefault('LOG_DIR',tmpdir)
os.environ.setdefault('SECRET_KEY','diag')
os.environ.setdefault('FLASK_ENV','testing')
os.environ.setdefault('SITE_URL','https://glory2yah.net')

from app import create_app
app = create_app()
with app.app_context():
    from jinja2 import meta
    env = app.jinja_env
    src = app.jinja_loader.get_source(env, 'ad_detail.html')[0]
    print(f"TEMPLATE SIZE: {len(src)} CHARS")
    try:
        ast = env.parse(src)
        print("PARSE OK")
    except Exception as e:
        print(f"PARSE FAIL: {type(e).__name__}: {e}")
        import traceback; traceback.print_exc()
    # Print chars around 8760 -> 8780
    i = 8760
    print(f"\nCHARS around index {i}:")
    for p in range(max(0, i-30), min(len(src), i+30)):
        c = src[p]
        print(f"  {p}: {repr(c)} ord={ord(c)}")
    sys.exit(0)
