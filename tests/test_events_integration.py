"""test_events_integration.py

Evaluate how well the EVENTS module (SOS ALO LEGLIZ) is integrated into the
Glory2YahPub Flask application.

Contract under test — see ``events/backend/API-REFERENCE.md`` and
``events/backend/README-INTEGRATION.md``:

  * ``app/models/events.py``  -> SQLAlchemy models (Event, EventLeader, ...)
  * ``seed_events()``         -> idempotent bootstrap seed of the
                                 SOS ALO LEGLIZ event (status='draft')
  * blueprints/routes         -> public landing + admin endpoints
  * templates                 -> landing page served

Run:
    python tests/test_events_integration.py

Exit code:
    0  -> every check PASSED (module fully integrated)
    1  -> evaluation itself crashed
    2  -> at least one FAIL (module missing / partially integrated)
"""
import os
import sys

# Allow running directly:  python tests/test_events_integration.py
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Make console output ascii/cp1252-safe so unicode from the app logs or the
# report cannot crash the script on Windows terminal encodings.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# --------------------------------------------------------------------------
# Expected contract (mirrors events/backend/migrations/001_create_events_schema.sql
# and the Flask port in app/models/events.py)
# --------------------------------------------------------------------------
EXPECTED_MODELS = [
    "Event", "EventLeader", "EventProgramItem", "EventFaq", "EventNews",
    "EventMedia", "EventRegion", "EventCoordinator", "EventParticipant",
    "EventOrganization",  # referenced by Event.organizations (must exist)
]

EXPECTED_TABLES = [
    "events", "event_leaders", "event_program_items", "event_faq",
    "event_news", "event_media", "event_regions", "event_coordinators",
    "event_participants", "event_organizations",
]

SEED_SLUG = "sos-alo-legliz"


class Check:
    """One result line of the evaluation."""

    def __init__(self, section, title, ok, detail=""):
        self.section = section
        self.title = title
        self.ok = bool(ok)
        self.detail = detail

    def __str__(self):
        head = f"[{'PASS' if self.ok else 'FAIL'}] ({self.section}) {self.title}"
        return head + (f"\n        -> {self.detail}" if self.detail else "")


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def _file_exists(path):
    return os.path.isfile(path)


def _db_table_names(app):
    """Return the set of table names physically present on the app's engine."""
    from sqlalchemy import inspect as sa_inspect
    from app import db
    with app.app_context():
        return set(sa_inspect(db.engine).get_table_names())


def _url_rules(app):
    rules = []
    for rule in app.url_map.iter_rules():
        rules.append(rule.rule)
    return rules


def _is_event_route(rule):
    lr = rule.strip("/").lower()
    if not lr:
        return False
    # /pwa/api/events is the PWA install-tracking endpoint (AppInstallation),
    # NOT the SOS ALO LEGLIZ events module. /fet is the party module. Exclude both.
    if lr.startswith(("pwa/", "fet", "api/")):
        return False
    return "event" in lr or "evenement" in lr or "sos-alo" in lr


# --------------------------------------------------------------------------
# PART A — Models
# --------------------------------------------------------------------------
def run_model_checks(app, checks):
    path = os.path.join(_ROOT, "app", "models", "events.py")
    src = _read_text(path)

    checks.append(Check("models", "app/models/events.py exists", bool(src),
                        path if src else "file missing / unreadable"))
    if not src:
        return

    # Snapshot metadata BEFORE importing the events module ourselves, so our own
    # import cannot fake "registered" state the app does not actually have.
    from app import db
    with app.app_context():
        meta_before = set(db.metadata.tables) if getattr(db, "metadata", None) else set()
    baseline = sorted(meta_before & set(EXPECTED_TABLES))

    try:
        mod = __import__("app.models.events", fromlist=["*"])
        defined = {n for n in dir(mod) if n in EXPECTED_MODELS}
        checks.append(Check("models", "app.models.events imports cleanly", True,
                            "classes found: " + ", ".join(sorted(defined))
                            if defined else "module imports but none of the classes"))
    except Exception as exc:
        checks.append(Check("models", "app.models.events imports cleanly", False,
                            f"{type(exc).__name__}: {exc}"))
        defined = set()

    missing = [n for n in EXPECTED_MODELS if n not in defined]
    checks.append(Check("models", "all expected model classes defined", not missing,
                        (", ".join(missing) + " MISSING") if missing
                        else "all 10 present"))

    checks.append(Check("bootstrap", "seed_events() defined in events.py",
                        "def seed_events" in src, ""))

    # Models registered in SQLAlchemy metadata => tables would be created.
    # PASS only if the APP'S OWN code already wires the module, i.e. the
    # baseline snapshot (taken before our test import) had the event tables.
    imported_by = []
    for rel in ["app/models/__init__.py", "app/__init__.py"]:
        txt = _read_text(os.path.join(_ROOT, rel))
        if "models.events" in txt or "from app.models.events" in txt:
            imported_by.append(rel)
    checks.append(Check(
        "models",
        "events models registered in SQLAlchemy metadata by the app",
        bool(baseline) or bool(imported_by),
        f"tables present before test import: {baseline or 'NONE'} | "
        f"imported by: {imported_by or 'nowhere (event tables are NEVER created)'}",
    ))


# --------------------------------------------------------------------------
# PART B — Routes / blueprint wiring
# --------------------------------------------------------------------------
def run_route_checks(app, checks):
    init_src = _read_text(os.path.join(_ROOT, "app", "__init__.py"))
    mod_init_src = _read_text(os.path.join(_ROOT, "app", "models", "__init__.py"))

    wired = ("models.events" in init_src) or ("events" in mod_init_src)
    checks.append(Check(
        "routes",
        "events models wired into app bootstrap imports",
        wired,
        "" if wired else
        "app/__init__.py model-load block + app/models/__init__.py never "
        "import app.models.events",
    ))

    checks.append(Check(
        "routes",
        "events blueprint registered in register_blueprints()",
        "events" in init_src,
        "",
    ))

    rules = _url_rules(app)
    ev_rules = [r for r in rules if _is_event_route(r)]
    checks.append(Check(
        "routes",
        "URL map exposes an events route",
        bool(ev_rules),
        ("routes: " + ", ".join(sorted(ev_rules))) if ev_rules
        else "no events route registered (existing /fet is the party module)",
    ))

    # This app uses plain routes (/events, /admin/events) rather than an
    # /api/... prefix (marketplace=/mache, admin=/admin, ...). Accept either
    # convention as long as the event routes are actually registered.
    evt_route_sigs = sorted({r for r in rules
                             if _is_event_route(r)
                             or ("admin/" in r and "event" in r.lower())})
    apis = {r for r in rules if "/api/" in r and "event" in r.lower()
            and not r.lower().startswith("/pwa")}
    registered = bool(evt_route_sigs) or bool(apis)
    checks.append(Check(
        "routes",
        "event routes registered (app convention /events, /admin/events)",
        registered,
        "endpoints: " + ", ".join(sorted(apis | set(evt_route_sigs))) if registered
        else "no /events or /admin/events routes, no /api/events* endpoints",
    ))


# --------------------------------------------------------------------------
# PART C — Database runtime
# --------------------------------------------------------------------------
def run_db_checks(app, checks):
    try:
        tables = _db_table_names(app)
    except Exception as exc:
        checks.append(Check("database", "could not introspect app DB", False,
                            f"{type(exc).__name__}: {exc}"))
        return

    present = sorted(set(EXPECTED_TABLES) & tables)
    missing = sorted(set(EXPECTED_TABLES) - tables)
    checks.append(Check(
        "database",
        "event_* tables created by the app's db.create_all()",
        bool(present),
        ("created: " + ", ".join(present)) if present
        else "NONE exist -> the module is not registered with SQLAlchemy, "
             "so create_all() ignores it",
    ))
    if missing:
        checks.append(Check("database", "all expected event_* tables created",
                            False, "missing: " + ", ".join(missing)))

    seeded = False
    try:
        from app import db
        from sqlalchemy import text
        if "events" in tables:
            with app.app_context():
                row = db.session.execute(
                    text("SELECT slug FROM events WHERE slug = :s LIMIT 1"),
                    {"s": SEED_SLUG},
                ).fetchone()
                seeded = row is not None
    except Exception:
        seeded = False
    checks.append(Check(
        "database",
        f"SOS ALO LEGLIZ ({SEED_SLUG}) present after bootstrap",
        seeded,
        "" if seeded else "no seeded event row -> seed_events() never ran",
    ))


# --------------------------------------------------------------------------
# PART D — Frontend / templates
# --------------------------------------------------------------------------
def run_template_checks(app, checks):
    present = []
    if _file_exists(os.path.join(_ROOT, "templates", "create_event.html")):
        present.append("templates/create_event.html")
    if _file_exists(os.path.join(_ROOT, "events", "frontend", "sos-alo-legliz.html")):
        present.append("events/frontend/sos-alo-legliz.html")
    checks.append(Check("frontend", "event landing templates shipped",
                        bool(present),
                        ("present: " + ", ".join(present)) if present
                        else "no event template found"))


# --------------------------------------------------------------------------
# Report / main
# --------------------------------------------------------------------------
def _report(checks):
    for c in checks:
        print(c)
    print()
    print("-" * 78)
    fails = [c for c in checks if not c.ok]
    print(f"SUMMARY: {len(checks) - len(fails)}/{len(checks)} checks passed | "
          f"{len(fails)} FAILED")
    for c in fails:
        print(f"  x ({c.section}) {c.title}")
    if fails:
        print()
        print("VERDICT: EVENTS MODULE IS NOT FULLY INTEGRATED.")
        print("To integrate, wire the module into the running Flask app:")
        print("  1. Import the models in the bootstrap: app/__init__.py "
              "'Import all models' block + app/models/__init__.py")
        print("     from app.models.events import (Event, EventLeader, ...)")
        print("  2. Add the missing seed_events() function and call it after "
              "db.create_all() (see events/backend/README-INTEGRATION.md).")
        print("  3. Add an events Blueprint with the routes in "
              "events/backend/API-REFERENCE.md and register it in "
              "register_blueprints() (there is currently NO events blueprint).")
        print("  4. Serve the landing page at /evenements/sos-alo-legliz "
              "(templates/create_event.html / events/frontend/sos-alo-legliz.html).")
        return 2
    print()
    print("VERDICT: EVENTS MODULE IS FULLY INTEGRATED.")
    return 0


def main():
    print("=" * 78)
    print("EVENTS (SOS ALO LEGLIZ) - INTEGRATION EVALUATION")
    print("=" * 78)
    print("(uses a throwaway 'testing' in-memory DB; your data is untouched)\n")

    try:
        from app import create_app
        app = create_app("testing")
    except Exception as exc:
        import traceback
        print(f"Could not create the app instance for runtime checks: "
              f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
        return 1

    checks = []
    # Order matters: model/import checks, then routes, then DB, then templates.
    run_model_checks(app, checks)
    run_route_checks(app, checks)
    run_db_checks(app, checks)
    run_template_checks(app, checks)
    return _report(checks)


if __name__ == "__main__":
    try:
        _code = main()
    except Exception as exc:  # evaluation crashed -> fail loudly
        import traceback
        traceback.print_exc()
        print(f"\nEVALUATION CRASHED: {type(exc).__name__}: {exc}")
        _code = 1
    raise SystemExit(_code)