"""KONFERANS frontend screenshot + console-error capture (diagnostic only)."""
import os, sys
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5000"
OUT = "_konf_screens"
os.makedirs(OUT, exist_ok=True)

ROOM_CODE = "VD1R78"  # existing active room (no password)

def shoot(page, name):
    page.wait_for_timeout(1500)
    page.screenshot(path=f"{OUT}/{name}.png", full_page=True)
    print(f"  shot {name}.png  url={page.url}  title={page.title()!r}")

def main():
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        # seed a logged-in session via the real login form (test user)
        page = ctx.new_page()
        page.on("console", lambda m: errors.append(f"[{page.url}] {m.type}: {m.text}") if m.type in ("error","warning") else None)
        page.on("pageerror", lambda e: errors.append(f"[{page.url}] PAGEERROR: {e}"))

        # 1) index (guest)
        page.goto(BASE + "/konferans/", wait_until="networkidle")
        shoot(page, "01_index_guest")

        # 2) room page as guest (owner controls should be hidden)
        page.goto(BASE + f"/konferans/room/{ROOM_CODE}?user_name=Tester", wait_until="networkidle")
        shoot(page, "02_room_guest")

        # 3) room scrolled to controls / media area
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            shoot(page, "03_room_bottom")
        except Exception as e:
            print("join step skip:", e)

        ctx.close()
        browser.close()

    print("\n===== CONSOLE / PAGE ERRORS =====")
    with open(f"{OUT}/_errors.txt", "w", encoding="utf-8") as fh:
        if not errors:
            fh.write("(none)\n")
        for e in errors[:120]:
            fh.write(e + "\n")
    print(f"wrote {len(errors)} error lines to {OUT}/_errors.txt")

if __name__ == "__main__":
    main()
