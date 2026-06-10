# MANDEMMAPBAW - Debug Instructions

## Common Issues and Solutions

### Issue 1: Backend doesn't respond / 500 errors

**Possible Causes:**
1. Missing dependencies
2. Database not initialized
3. Import errors
4. Port already in use

**Solutions:**

#### A. Check Dependencies

```bash
# Install minimal dependencies first (no AI)
pip install -r requirements-minimal.txt

# Then test
python test_app.py
```

#### B. Check for Errors

```bash
# Run with verbose output
python -c "from app import app; print('OK')" 2>&1

# Check specific imports
python -c "from database.models import db; print('DB OK')"
python -c "from models import *; print('Models OK')" 2>&1 || echo "Models failed (expected if no AI deps)"
```

#### C. Initialize Database

```bash
python -c "from app import app, db; app.app_context().push(); db.create_all(); print('DB created')"
```

#### D. Run in Simple Mode (No AI)

```bash
# This works without AI dependencies
python run_simple.py
```

### Issue 2: ModuleNotFoundError

**Error:** `ModuleNotFoundError: No module named 'torch'` or similar

**Solution:**
```bash
# Either install full dependencies
pip install -r requirements.txt

# Or use simple mode
python run_simple.py
```

### Issue 3: Circular Import

**Error:** `ImportError: cannot import name 'db' from partially initialized module`

**This should be fixed in the latest version.**

If you still see it:
1. Check that `database/models.py` creates `db = SQLAlchemy()`
2. Check that `app.py` does `db.init_app(app)` NOT `db = SQLAlchemy(app)`

### Issue 4: Port Already in Use

**Error:** `OSError: [Errno 98] Address already in use`

**Solution:**
```bash
# Find and kill process on port 5000
lsof -ti:5000 | xargs kill -9

# Or use different port
export FLASK_PORT=8000
python app.py
```

### Issue 5: Database Locked

**Error:** `sqlite3.OperationalError: database is locked`

**Solution:**
```bash
rm mandemmapbaw.db
python -c "from app import app, db; app.app_context().push(); db.create_all()"
```

## Testing Checklist

Run these commands in order:

```bash
# 1. Check Python version
python --version  # Should be 3.8+

# 2. Check dependencies
pip list | grep -E "Flask|SQLAlchemy|Pillow|numpy|opencv"

# 3. Run test script
python test_app.py

# 4. Initialize database
python -c "from app import app, db; app.app_context().push(); db.create_all()"

# 5. Start app
python app.py
# or for fallback only:
python run_simple.py
```

## Manual Testing

### Test with curl:

```bash
# Test homepage
curl http://localhost:5000/

# Test chat (with fallback)
curl -X POST http://localhost:5000/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Bonjou", "mode": "chat"}'

# Test stats
curl http://localhost:5000/admin/stats
```

### Expected Responses:

**Homepage:** Should return HTML
**Chat:** Should return JSON with response (even if fallback)
**Stats:** Should return JSON with counts

## Getting Detailed Errors

### Run with Python debugger:

```python
python -i << 'PYEOF'
from app import app

# Test creating app context
with app.app_context():
    from database.models import db
    db.create_all()
    print("Database created successfully")

# Test imports
try:
    from models.text_generator import TextGenerator
    print("Text generator imported OK")
except Exception as e:
    print(f"Text generator failed: {e}")

try:
    from models.video_generator import VideoGenerator
    print("Video generator imported OK")
except Exception as e:
    print(f"Video generator failed: {e}")

print("\nApp should be ready. Start with: app.run(debug=True)")
PYEOF
```

## Quick Fix Summary

If nothing works:

```bash
# 1. Clean install
rm -rf venv mandemmapbaw.db
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# 2. Install minimal deps
pip install -r requirements-minimal.txt

# 3. Create DB
python -c "from app import app, db; app.app_context().push(); db.create_all()"

# 4. Run simple mode
python run_simple.py
```

This should at least get the app running with fallback responses.

## Logs Location

Check these for errors:
- Console output (stderr)
- Flask logs (if logging configured)
- Browser console (F12) for frontend errors

## Contact

If still having issues, provide:
1. Full error message
2. Python version
3. Output of `pip list`
4. Output of `python test_app.py`
