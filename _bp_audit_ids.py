# Collect sample IDs from local DB for blueprint crawling
import io, sys, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from app import create_app, db
a = create_app()
with a.app_context():
    out = {}
    try:
        from app.models.ad import Ad
        ad = Ad.query.filter_by(admin_status="approved").first()
        out["ad_id"] = ad.id if ad else None
        ad_any = Ad.query.first()
        out["ad_id_any"] = ad_any.id if ad_any else None
    except Exception as e:
        out["ad_err"] = str(e)
    try:
        from app.models.user import User
        u = User.query.first()
        out["user_repr"] = [str(u.identifier) if hasattr(u, "identifier") else str(u) for u in User.query.limit(5)]
    except Exception as e:
        out["user_err"] = str(e)
    for mod, cls in [("konferans.models", None), ("party.models", None), ("mennem.models", None), ("ecole_biblique", None), ("app.models", None)]:
        pass
    # generic scan of all registered models for plausible id samples
    from sqlalchemy import inspect as sqlinspect, text
    insp = sqlinspect(db.engine)
    tables = insp.get_table_names()
    out["tables"] = tables
    for t in tables:
        try:
            with db.engine.connect() as conn:
                row = conn.execute(text(f"SELECT * FROM {t} LIMIT 1")).mappings().first()
                if row:
                    out[f"sample_{t}"] = {k: str(v)[:40] for k, v in dict(row).items() if k in ("id", "room_code", "code", "slug", "party_id", "trip_id", "room_id", "driver_id", "course_id", "class_id", "lesson_id", "assignment_id", "product_id", "short_id", "batch_id", "filename", "name", "pseudo", "identifier", "email")}
        except Exception:
            pass
    print(json.dumps(out, indent=1, ensure_ascii=False))
