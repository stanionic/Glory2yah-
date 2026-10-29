# Enumerate all registered blueprints + routes; report registration failures.
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from app import create_app

a = create_app()
print("BLUEPRINTS:", sorted(a.blueprints.keys()))
print("-" * 70)
seen = set()
for r in sorted(a.url_map.iter_rules(), key=lambda x: str(x.rule)):
    methods = ",".join(sorted(r.methods - {"HEAD", "OPTIONS"}))
    endpoint = r.endpoint
    bp = endpoint.split(".")[0] if "." in endpoint else "main_app"
    if str(r.rule) in seen:
        continue
    seen.add(str(r.rule))
    print(f"[{bp:15}] {methods:12} {r.rule}")
print("-" * 70)
print("TOTAL ROUTES:", len(seen))
