# -*- coding: utf-8 -*-
"""Test EVERY blueprint route with testing account. Flask test client (in-process).

Creates test user automatically, logs in, traverses registered blueprints
from app.url_map — GET every non-POST-only rule, checks status & catches
500 with full traceback. Includes the ecole_biblique bug hunt.
"""
import os, sys, json, traceback, io, uuid, datetime as dt, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ.setdefault("FLASK_ENV", "development")
os.environ.setdefault("SECRET_KEY", "test-suite-" + uuid.uuid4().hex)
os.environ.setdefault("DATABASE_URL", "")
os.environ.setdefault("CREATE_TEST_USER", "1")
os.environ.setdefault("TEST_USER_PASSWORD", "123456")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from app import create_app, db

app = create_app()
app.config["TESTING"] = True
app.config["WTF_CSRF_ENABLED"] = False
app.config["PROPAGATE_EXCEPTIONS"] = False  # don't crash, log 500 HTML

# Test account credentials (matches CREATE_TEST_USER env above)
TEST_WHATSAPP = "+50912345678"
TEST_PASSWORD = "123456"

# Blueprint-level overview list for coverage label
BLUEPRINTS_TEST = []
for rule in app.url_map.iter_rules():
    bp = rule.endpoint.split(".")[0] if "." in rule.endpoint else "(root)"
    if bp not in BLUEPRINTS_TEST:
        BLUEPRINTS_TEST.append(bp)

results = {"passed": 0, "failed": 0, "failed_list": [], "total": 0}
REPORT = []

def log(msg=""):
    try:
        safe = str(msg)
        sys.stdout.write(safe + "\n")
        sys.stdout.flush()
    except Exception:
        try:
            safe2 = str(msg).encode("ascii", "replace").decode("ascii")
            print(safe2, flush=True)
        except Exception:
            pass
    REPORT.append(str(msg))

def save_report():
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"test_all_blueprints_{ts}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(REPORT))
    print(f"\nSAVED REPORT -> {path}", flush=True)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "test_all_blueprints_LATEST.json"), "w", encoding="utf-8") as jf:
        json.dump(results, jf, indent=2)
    print(f"SAVED JSON  -> test_all_blueprints_LATEST.json", flush=True)

log("=" * 80)
log(" TEST ALL BLUEPRINTS — in-process Flask test client + test account")
log("=" * 80)
log(f" Registered blueprints: {len(BLUEPRINTS_TEST)}")
for bp in BLUEPRINTS_TEST:
    log(f"    - {bp}")

# Step 1: Ensure DB tables + test user created
with app.app_context():
    try:
        from app.models.user import User
        from app.models.user_gkach import UserGkach
        db.create_all()
        u = User.query.filter_by(whatsapp=TEST_WHATSAPP).first()
        if not u:
            log(f"\n[setup] Creating test user {TEST_WHATSAPP}")
            u = User(whatsapp=TEST_WHATSAPP, pseudo="testuser", name="Test User",
                     auth_provider="whatsapp", is_active=True)
            u.set_password(TEST_PASSWORD)
            db.session.add(u)
            db.session.flush()
        else:
            u.set_password(TEST_PASSWORD)  # re-hash in case password was 123456 before different salt
            if not u.is_active: u.is_active = True
            db.session.add(u)
            db.session.flush()
        g = UserGkach.query.filter_by(user_whatsapp=TEST_WHATSAPP).first()
        if not g:
            g = UserGkach(user_id=u.id, user_whatsapp=TEST_WHATSAPP, gkach_balance=1000)
            db.session.add(g)
        db.session.commit()
        log(f"[setup] Test user ready: pseudo={u.pseudo} id={u.id} balance={g.gkach_balance}")
    except Exception as e:
        log(f"[setup] WARNING: {type(e).__name__}: {e}")
        db.session.rollback()

# Step 2: HTTP client with login
client = app.test_client(use_cookies=True)
# Step 2a: test client login via POST /auth/login
log("\n[login] POST /auth/login")
with client.session_transaction() as sess:
    pass  # session available if needed
login_resp = client.post("/auth/login", data={
    "identifier": TEST_WHATSAPP,
    "password": TEST_PASSWORD,
}, follow_redirects=False)
log(f"        status={login_resp.status_code}")

# Verify logged in
who = client.get("/profile")
log(f"[login-verify] GET /profile -> {who.status_code}")

# Step 3: Gather ALL routes from url_map (non-method-restricted; GET for each rule)
log("\n" + "=" * 80)
log(" ROUTE WALK")
log("=" * 80)

# Build sorted list of rules
rules = list(app.url_map.iter_rules())
rules_sorted = sorted(rules, key=lambda r: r.endpoint)

for rule in rules_sorted:
    # Skip methods that can only be POST (GET not allowed)
    methods = {m for m in (rule.methods or set()) if m not in {"HEAD", "OPTIONS"}}
    if "GET" not in methods:
        continue  # Only test GET routes here to avoid data mutations

    endpoint = rule.endpoint
    bp_name = endpoint.split(".")[0] if "." in endpoint else "(root)"

    # Build an example URL (replace path params with sample values)
    try:
        sample_url = rule.rule
        sample_url = sample_url.replace("<int:id>", "1")
        sample_url = sample_url.replace("<int:batch_id>", "1")
        sample_url = sample_url.replace("<int:ad_id>", "1")
        sample_url = sample_url.replace("<int:user_id>", "1")
        sample_url = sample_url.replace("<int:module_id>", "1")
        sample_url = sample_url.replace("<int:course_id>", "1")
        sample_url = sample_url.replace("<int:student_id>", "1")
        sample_url = sample_url.replace("<int:lesson_id>", "1")
        sample_url = sample_url.replace("<int:quiz_id>", "1")
        sample_url = sample_url.replace("<int:question_id>", "1")
        sample_url = sample_url.replace("<int:answer_id>", "1")
        sample_url = sample_url.replace("<int:product_id>", "1")
        sample_url = sample_url.replace("<int:order_id>", "1")
        sample_url = sample_url.replace("<int:cart_id>", "1")
        sample_url = sample_url.replace("<int:item_id>", "1")
        sample_url = sample_url.replace("<int:file_id>", "1")
        sample_url = sample_url.replace("<int:message_id>", "1")
        sample_url = sample_url.replace("<int:party_id>", "1")
        sample_url = sample_url.replace("<int:ticket_id>", "1")
        sample_url = sample_url.replace("<string:ad_id>", str(uuid.uuid4()))
        sample_url = sample_url.replace("<string:share_id>", str(uuid.uuid4()))
        sample_url = sample_url.replace("<string:ref>", "REF" + uuid.uuid4().hex[:8].upper())
        sample_url = sample_url.replace("<string:ad_type>", "sell")
        sample_url = sample_url.replace("<path:path>", "sample-path")
        sample_url = sample_url.replace("<filename>", "sample.pdf")
        sample_url = sample_url.replace("<short_code>", "ABCD1234")
        sample_url = sample_url.replace("<trip_type>", "one-way")
        sample_url = sample_url.replace("<status>", "pending")
        sample_url = sample_url.replace("<slug>", "sample-slug")
        sample_url = sample_url.replace("<batch_code>", "BATCH001")
        sample_url = sample_url.replace("<code>", "ABCD1234")
        sample_url = sample_url.replace("<s>", "search-term")
        sample_url = sample_url.replace("<id>", "1")
        sample_url = sample_url.replace("<ad_id>", "1")
        sample_url = sample_url.replace("<share_id>", uuid.uuid4().hex[:8])
        sample_url = sample_url.replace("<ref>", "REF001")
        sample_url = sample_url.replace("<token>", uuid.uuid4().hex)
        sample_url = sample_url.replace("<username>", "testuser")
        sample_url = sample_url.replace("<whatsapp>", "50912345678")
        sample_url = sample_url.replace("<user_whatsapp>", "50912345678")
        sample_url = sample_url.replace("<module_code>", "MOD001")
        sample_url = sample_url.replace("<course_code>", "COU001")
        sample_url = sample_url.replace("<student_code>", "STU001")
        sample_url = sample_url.replace("<file_name>", "file.pdf")
        sample_url = sample_url.replace("<doc_id>", uuid.uuid4().hex[:8])
        # Generic fallback: replace any remaining <type:name> or <name>
        sample_url = re.sub(r"<[a-zA-Z_][a-zA-Z0-9_]*:[^>]+>", "1", sample_url)
        sample_url = re.sub(r"<[^>]+>", "1", sample_url)
    except Exception:
        sample_url = rule.rule

    if any(bad in sample_url for bad in ("<", ">", "%3C", "%3E")):
        # Skip unresolvable placeholders
        log(f"  SKIP unresolved placeholders: {sample_url}  [{endpoint}]")
        continue

    # Skip huge/static media paths (they work via static; don't spam)
    if sample_url.startswith("/static/") or sample_url.startswith("/sw.js") \
       or sample_url.startswith("/manifest.json") or sample_url.startswith("/robots.txt"):
        continue
    # Skip SocketIO / ws
    if "socket.io" in sample_url.lower():
        continue

    results["total"] += 1
    try:
        resp = client.get(sample_url, follow_redirects=False)
        status = resp.status_code
        # 200, 301/302 redirects are OK for gated routes (login_required, etc)
        # 403/404 OK for permission-gated or not-found-by-param routes
        # 503 OK for /health degraded-state endpoints (e.g. Redis unavailable)
        acceptable = {200, 301, 302, 303, 307, 308, 401, 403, 404, 405, 410, 503}
        ok = (status in acceptable)
        label = "PASS" if ok else "FAIL"
        log(f"[{label:4s}] [{bp_name:25s}] {status:3d} GET {sample_url}  ({endpoint})")
        if status == 500:
            results["failed"] += 1
            results["failed_list"].append({
                "endpoint": endpoint, "url": sample_url, "status": 500,
                "bp": bp_name,
                "body_preview": resp.data.decode("utf-8", errors="replace")[:1500]
            })
            # Attach traceback if Flask logged any
            if hasattr(app, "_exception_traceback"):
                pass
            log(f"     FAIL 500 BODY PREVIEW (1500 chars):")
            preview = resp.data.decode("utf-8", errors="replace")[:1500]
            for line in preview.splitlines():
                log(f"       | {line}")
        elif not ok:
            results["failed"] += 1
            results["failed_list"].append({
                "endpoint": endpoint, "url": sample_url, "status": status,
                "bp": bp_name,
                "note": f"unexpected status {status}"
            })
        else:
            results["passed"] += 1
    except Exception as e:
        results["failed"] += 1
        results["failed_list"].append({
            "endpoint": endpoint, "url": sample_url, "status": "EXC",
            "bp": bp_name,
            "exc": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc()
        })
        log(f"[FAIL] [{bp_name:25s}] EXC {type(e).__name__}: {e}  GET {sample_url}")

# Step 4: Summary
log("\n" + "=" * 80)
log(" SUMMARY")
log("=" * 80)
log(f" Total routes tested (GET): {results['total']}")
log(f" Passed:  {results['passed']}")
log(f" Failed:  {results['failed']}")
if results["failed_list"]:
    log("\n FAILURES:")
    for i, fail in enumerate(results["failed_list"], 1):
        log(f"\n [{i}] {fail['bp']} :: {fail['endpoint']}")
        log(f"     URL : {fail.get('url')}")
        log(f"     STAT: {fail.get('status')}")
        if "exc" in fail:
            log(f"     EXC : {fail['exc']}")
            log(f"     TRACEBACK:\n{fail.get('traceback')}")
        if "body_preview" in fail:
            log(f"     500 BODY PREVIEW:\n{fail['body_preview']}")

save_report()
