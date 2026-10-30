"""KONFERANS owner-view screenshot + console-error capture (diagnostic only)."""
import os
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5000"
OUT = "_konf_screens"
os.makedirs(OUT, exist_ok=True)
OWNER = {"identifier": "+50948592888", "password": "pass123"}
ROOM_CODE = "UBTKE6"  # owned by user 6

def shoot(page, name):
    page.wait_for_timeout(1500)
    page.screenshot(path=f"{OUT}/{name}.png", full_page=True)
    print(f"  shot {name}.png url={page.url}")

def main():
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        page = ctx.new_page()
        page.on("console", lambda m: errors.append(f"[{page.url}] {m.type}: {m.text}") if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: errors.append(f"[{page.url}] PAGEERROR: {e}"))

        # login
        page.goto(BASE + "/auth/login", wait_until="networkidle")
        # dismiss PWA install modal if it overlays the form
        try:
            for sel in [".pwa-popup-dismiss-btn", ".pwa-ios-dismiss-btn"]:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    el.click(); page.wait_for_timeout(400); break
        except Exception as e:
            print("modal dismiss skip:", e)
        page.fill("input[name='identifier']", OWNER["identifier"])
        page.fill("input[name='password']", OWNER["password"])
        page.click("#loginSubmit")
        page.wait_for_timeout(3000)
        print("post-login url:", page.url)
        shoot(page, "10_after_login")

        # owner room
        page.goto(BASE + f"/konferans/room/{ROOM_CODE}?user_name=Owner", wait_until="networkidle")
        shoot(page, "11_room_owner")

        ctx.close(); browser.close()

    with open(f"{OUT}/_errors_owner.txt", "w", encoding="utf-8") as fh:
        fh.write("\n".join(errors) if errors else "(none)")
    print(f"wrote {len(errors)} error lines")

if __name__ == "__main__":
    main()
