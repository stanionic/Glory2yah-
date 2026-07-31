# Debug Session: localhost-refused

Status: RESOLVED

Symptom:
- `http://localhost:8080` returned connection refused.

Root Cause:
- The application was not running. No previous server process was active on port 8080.

Resolution:
- Ran `python run.py` which successfully started the Flask/SocketIO server.
- The app is now listening on:
  - http://127.0.0.1:8080
  - http://10.181.67.244:8080
- Server responds with HTTP 200 on the home page.

Evidence:
- Import test: `from app import app` succeeds without errors.
- Server startup logs show all blueprints registered (PWA, ecole_biblique, mennem).
- Redis is unavailable (expected in dev without Redis) - app falls back to database-only mode gracefully.
- SocketIO running without Redis message queue (expected in dev).
- Database: SQLite connected successfully.
- Admin user and test user created on first run.

Next Steps:
- No further action needed. The app is running and accessible.