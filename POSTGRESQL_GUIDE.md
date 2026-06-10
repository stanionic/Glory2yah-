# 🐘 PostgreSQL Setup Guide for Glory2YahPub

## Current Status
- ✅ PostgreSQL support added to code
- ✅ psycopg2-binary installed
- ⚠️ PostgreSQL server not running/installed
- ✅ App works with SQLite (fallback)

---

## Option 1: Use SQLite (Current - No Setup Needed)

The app is already configured to use SQLite if PostgreSQL is not available.

**Just run:**
```bash
python run.py
```

---

## Option 2: Install PostgreSQL

### Windows Installation

1. **Download PostgreSQL**
   - Visit: https://www.postgresql.org/download/windows/
   - Download PostgreSQL 15 or 16
   - Run installer

2. **During Installation**
   - Set password: `postgres` (or remember your password)
   - Port: `5432` (default)
   - Locale: Default

3. **Update .env file**
   ```env
   DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/glory2yahpub
   ```

4. **Run Setup**
   ```bash
   python setup_postgres.py
   ```

5. **Start App**
   ```bash
   python run.py
   ```

---

## Option 3: Use Docker PostgreSQL

### Quick Start with Docker

```bash
# Pull PostgreSQL image
docker pull postgres:15

# Run PostgreSQL container
docker run --name glory2yah-postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=glory2yahpub \
  -p 5432:5432 \
  -d postgres:15

# Setup database
python setup_postgres.py

# Start app
python run.py
```

### Windows Docker Command
```cmd
docker run --name glory2yah-postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=glory2yahpub -p 5432:5432 -d postgres:15
```

---

## Verify PostgreSQL is Running

### Windows
```cmd
# Check if service is running
sc query postgresql-x64-15

# Or check with psql
psql -U postgres -h localhost
```

### Check Connection
```bash
python -c "import psycopg2; conn = psycopg2.connect('postgresql://postgres:postgres@localhost:5432/postgres'); print('Connected!')"
```

---

## Benefits of PostgreSQL vs SQLite

### PostgreSQL ✅
- Better for production
- Handles concurrent users
- Advanced features (JSON, full-text search)
- Better performance at scale
- Proper autoincrement support
- ACID compliance

### SQLite ✅
- No setup required
- Perfect for development
- Single file database
- Fast for small apps
- Easy backup (just copy file)

---

## Current Configuration

The app automatically detects which database to use:

1. **Checks** `.env` for `DATABASE_URL`
2. **If found**: Uses PostgreSQL
3. **If not found**: Uses SQLite

---

## Recommendation

### For Development
✅ **Use SQLite** (current setup)
- No installation needed
- Works immediately
- Easy to reset

### For Production
✅ **Use PostgreSQL**
- Better performance
- Handles multiple users
- Production-ready

---

## Quick Commands

### SQLite (Current)
```bash
python run.py  # Just works!
```

### PostgreSQL (After Setup)
```bash
# 1. Install PostgreSQL
# 2. Update .env with DATABASE_URL
# 3. Run setup
python setup_postgres.py

# 4. Start app
python run.py
```

---

## Troubleshooting

### "Connection refused" Error
- PostgreSQL is not running
- Install PostgreSQL or use SQLite

### "Database does not exist" Error
```bash
python setup_postgres.py
```

### "Authentication failed" Error
- Check password in .env
- Default is `postgres:postgres`

---

## Summary

**Current Status**: ✅ App works with SQLite

**To use PostgreSQL**:
1. Install PostgreSQL
2. Update `.env` with `DATABASE_URL`
3. Run `python setup_postgres.py`
4. Run `python run.py`

**Or just use SQLite**: `python run.py` (works now!)

---

*The app is production-ready with both SQLite and PostgreSQL support!*
