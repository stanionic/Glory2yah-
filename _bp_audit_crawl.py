# Blueprint-wide screenshot diagnosis crawl (anonymous + admin sessions).
import io, sys, os, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5000"
OUT = "_bp_audit_screens"
os.makedirs(OUT, exist_ok=True)
ADMIN = {"identifier": "Admin509", "password": "StanGlory2YahPub1986"}

IDS = {
    "ad_id": "DEMO-SELL-002", "batch_id": "3", "event_slug": "sos-alo-legliz",
    "room_code": "VD1R78", "room_id": "79dd8e2f-e5b5-47b7-8bf1-774c54aa3337",
    "ecole_course": "1", "ecole_module": "1", "jb_slug": "gloryah", "jb_pid": "1",
    "loan_product": "1", "inv_product": "1", "driver": "1", "cause_id": "1",
}

ANON = ["/", "/health", "/about", "/contact", "/privacy", "/terms", "/demo", "/tv",
        "/gadematch", "/search?q=test", "/mache/", "/mache/categories",
        "/mache/api/products", "/pwa/offline", "/gloryah-ia/", "/dok/health", "/dok/",
        "/s/create", f"/ad/{IDS['ad_id']}", f"/s/b/{IDS['batch_id']}",
        f"/events", f"/events/{IDS['event_slug']}", f"/events/{IDS['event_slug']}/locations",
        "/ecole_biblique/", "/ecole_biblique/login", "/ecole_biblique/register",
        "/ecole_biblique/ranking", "/ecole_biblique/live_classes",
        "/fet/", "/fet/kreye", "/mennenm/", "/mennenm/find", "/mennenm/register_driver",
        "/bank/", "/e-learning/", "/jere-biznis/", f"/jere-biznis/site/{IDS['jb_slug']}",
        "/forms/", "/cart/", "/auth/login", "/auth/register", "/admin/login",
        f"/konferans/check_room/{IDS['room_code']}",
        f"/jere-biznis/api/status", f"/jere-biznis/api/overview",
        f"/pwa/api/settings", f"/pwa/api/stats"]

AUTH = ["/auth/profile", "/auth/ads", "/auth/stories", "/submit_ad", "/achte_gkach",
        "/mache/", f"/mache/search?q=a", f"/mache/categories",
        f"/ad/{IDS['ad_id']}", f"/api/feed", "/api/notifications", "/api/stories",
        "/api/ads/trending", "/api/gkach/balance",
        "/cart/", f"/cart/api/count", "/cart/checkout",
        "/gkach/", "/gkach/wallet", "/gkach/rewards/dashboard",
        "/delivery/my-deliveries",
        "/admin/", "/admin/ads", "/admin/alerts", "/admin/audit", "/admin/rewards",
        "/admin/users", f"/admin/users/1", f"/admin/ad/{IDS['ad_id']}",
        "/admin/events", f"/admin/events/{IDS['event_slug']}/participants",
        f"/admin/events/{IDS['event_slug']}/organizations",
        "/admin/db-migration", "/admin/gkach/manage", "/admin/charity/donations",
        f"/admin/api/popup_settings",
        "/konferans/", f"/konferans/room/{IDS['room_code']}",
        f"/konferans/api/billing/{IDS['room_id']}",
        f"/konferans/api/stream/platforms",
        "/ecole_biblique/", "/ecole_biblique/student", "/ecole_biblique/teacher",
        f"/ecole_biblique/module/{IDS['ecole_module']}", "/ecole_biblique/modules",
        "/ecole_biblique/admin", "/ecole_biblique/admin/students",
        "/ecole_biblique/admin/payments", "/ecole_biblique/admin/graduation",
        "/ecole_biblique/admin/admission_results", "/ecole_biblique/admission_test",
        f"/ecole_biblique/api/grades/{IDS['ecole_course']}",
        "/fet/", f"/fet/my-parties", f"/fet/admin/parties",
        "/mennenm/admin", "/mennenm/my-trips", f"/mennenm/book/{IDS['driver']}/Port-au-Prince/Papelete",
        "/bank/", "/bank/loans", "/bank/investments", "/bank/investments/my", "/bank/admin",
        "/e-learning/", "/e-learning/student", "/e-learning/teacher",
        "/e-learning/classes/new", "/e-learning/courses/new",
        "/jere-biznis/", f"/jere-biznis/api/landing-pages",
        "/jere-biznis/api/subscription",
        "/dok/", "/forms/", "/search?q=ad"]


def shot_name(url):
    return (url.strip("/").replace("/", "_").replace("?", "_").replace("&", "_")
            .replace("<", "").replace(">", "").replace("{", "").replace("}", "") or "root")[:80]


def crawl(context, pages, tag, findings):
    page = context.new_page()
    console_errs, http_errs = [], []
    page.on("console", lambda m: console_errs.append(m.text[:300]) if m.type == "error" else None)
    def on_resp(r):
        if (r.status >= 400) and not any(x in r.url for x in ("/static/", "favicon", ".js", ".css", ".png", ".woff")):
            http_errs.append(f"{r.status} {r.url.replace(BASE,'')}")
    page.on("response", on_resp)
    for url in pages:
        console_errs.clear(); http_errs.clear()
        try:
            resp = page.goto(BASE + url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(900)
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass
            final = page.url.replace(BASE, "")
            status = resp.status if resp else 0
            body = ""
            try:
                body = page.inner_text("body")[:400]
            except Exception:
                pass
            rec = {"url": url, "status": status, "final": final,
                   "http_errors": list(http_errs), "console_errors": list(console_errs)[:5],
                   "snippet": " ".join(body.split())[:160]}
            if status >= 400 or http_errs or ("Error 500" in body) or ("Internal Server Error" in body):
                rec["severity"] = "HIGH"
                findings.append(rec)
            elif any(k in body for k in ("Traceback", "Exception", "Error!")) or not body.strip():
                rec["severity"] = "MED"
                findings.append(rec)
            rec["tag"] = tag
            print(json.dumps(rec, ensure_ascii=False))
            page.screenshot(path=f"{OUT}/{tag}__{shot_name(url)}.png")
        except Exception as e:
            rec = {"url": url, "tag": tag, "severity": "CRASH", "error": str(e)[:200]}
            findings.append(rec)
            print(json.dumps(rec, ensure_ascii=False))
    page.close()


def main():
    findings = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        # --- anonymous session ---
        anon_ctx = browser.new_context(viewport={"width": 1360, "height": 860})
        crawl(anon_ctx, ANON, "anon", findings)
        anon_ctx.close()
        # --- admin session ---
        adm_ctx = browser.new_context(viewport={"width": 1360, "height": 860})
        lp = adm_ctx.new_page()
        lp.goto(BASE + "/auth/login", wait_until="networkidle")
        lp.fill("input[name='identifier']", ADMIN["identifier"])
        lp.fill("input[name='password']", ADMIN["password"])
        lp.click("button[type='submit'], input[type='submit']")
        lp.wait_for_timeout(2500)
        lp.goto(BASE + "/auth/profile", wait_until="domcontentloaded")
        lp.wait_for_timeout(1200)
        logged_in = "Admin509" in lp.inner_text("body") or "rofile" in lp.url
        print(f"ADMIN_LOGIN_OK={logged_in} final={lp.url}")
        lp.close()
        if logged_in:
            crawl(adm_ctx, AUTH, "admin", findings)
        adm_ctx.close()
        browser.close()
    with open("_bp_audit_findings.json", "w", encoding="utf-8") as f:
        json.dump(findings, f, indent=1, ensure_ascii=False)
    print(f"\n=== FINDINGS: {len(findings)} suspicious pages ===")
    for fd in findings:
        print(json.dumps(fd, ensure_ascii=False))


if __name__ == "__main__":
    main()
