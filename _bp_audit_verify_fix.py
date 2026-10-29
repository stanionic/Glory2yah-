# Post-fix verification: re-check previously broken routes with real browser + screenshots.
import io, sys, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5000"
ADMIN = {"identifier": "Admin509", "password": "StanGlory2YahPub1986"}

CHECKS = [
    "/admin/events",            # was HTTP 500 (TypeError)
    "/admin/gkach/manage",      # was HTTP 500 (blueprint AssertionError)
    "/fet/my-parties",          # was HTTP 500 (Jinja endblock)
    "/cart/api/count",          # JSON, new correct path from base.html
    "/pwa/api/settings",        # JSON, new correct path from install.js
    "/mache/",                  # regressif: badge/count OK
]

results = []
with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1360, "height": 860})
    page = ctx.new_page()
    # login as admin
    page.goto(BASE + "/auth/login", wait_until="networkidle")
    page.fill("input[name='identifier']", ADMIN["identifier"])
    page.fill("input[name='password']", ADMIN["password"])
    page.click("button[type='submit'], input[type='submit']")
    page.wait_for_timeout(2500)
    bad_subresources = []
    page.on("response", lambda r: bad_subresources.append(f"{r.status} {r.url.replace(BASE,'')}")
            if r.status >= 400 and "/api/" in r.url else None)
    for url in CHECKS:
        bad_subresources.clear()
        resp = page.goto(BASE + url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(1200)
        try:
            body = page.inner_text("body")[:300]
        except Exception:
            body = ""
        status = resp.status if resp else 0
        ok = status == 200 and "ERRE 500" not in body.upper() and "pa jwenn" not in body[:120]
        name = url.strip("/").replace("/", "_").replace("?", "_")[:60]
        page.screenshot(path=f"_bp_audit_screens/FIXED__{name}.png")
        results.append({"url": url, "status": status, "ok": ok,
                        "subapi_errors": list(bad_subresources),
                        "snippet": " ".join(body.split())[:120]})
    browser.close()

for r in results:
    print(json.dumps(r, ensure_ascii=False))
print("ALL_OK =", all(r["ok"] for r in results))
