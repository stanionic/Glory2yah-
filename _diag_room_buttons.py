"""Diagnose konferans room page: capture JS console errors and test buttons."""
import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5000"
console_msgs, page_errors, failed_reqs = [], [], []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=[
        "--use-fake-ui-for-media-stream",
        "--use-fake-device-for-media-stream",
        "--autoplay-policy=no-user-gesture-required",
    ])
    ctx = browser.new_context(permissions=["camera", "microphone"])
    page = ctx.new_page()
    page.on("console", lambda m: console_msgs.append(f"[{m.type}] {m.text}"))
    page.on("pageerror", lambda e: page_errors.append(str(e)))
    page.on("requestfailed", lambda r: failed_reqs.append(f"{r.url} :: {r.failure}"))
    page.on("response", lambda r: failed_reqs.append(f"HTTP {r.status} {r.url}") if r.status >= 400 else None)
    page.on("dialog", lambda d: d.dismiss())

    # login
    page.goto(f"{BASE}/auth/login", wait_until="domcontentloaded", timeout=20000)
    page.fill("input[name='identifier']", "testuser")
    page.fill("input[name='password']", "123456")
    page.click("button[type='submit']")
    page.wait_for_timeout(3000)
    print("logged in, url =", page.url)

    # open room
    page.goto(f"{BASE}/konferans/room/EE8327?user_name=Test%20User", wait_until="domcontentloaded", timeout=20000)
    page.wait_for_timeout(4000)

    # report key state
    state = page.evaluate("""() => ({
        hasIO: typeof io !== 'undefined',
        hasSimplePeer: typeof SimplePeer !== 'undefined',
        socketConnected: (typeof socket !== 'undefined' && socket) ? socket.connected : null,
        localStreamTracks: (typeof localStream !== 'undefined' && localStream) ? localStream.getTracks().length : null,
        videoWrappers: document.querySelectorAll('.konf-video-wrapper').length,
    })""")
    print("STATE:", json.dumps(state))

    # click buttons and check side effects
    def click_test(sel, name):
        try:
            el = page.query_selector(sel)
            if not el:
                print(f"CLICK {name}: element NOT FOUND")
                return
            errs_before = len(page_errors)
            el.click()
            page.wait_for_timeout(1200)
            print(f"CLICK {name}: ok (new page errors: {len(page_errors)-errs_before})")
        except Exception as e:
            print(f"CLICK {name}: EXCEPTION {e}")

    click_test("#toggleVideo", "toggleVideo")
    click_test("#toggleAudio", "toggleAudio")
    click_test("#sendChat", "sendChat")
    page.wait_for_timeout(3000)
    msgs = page.evaluate("() => document.getElementById('chatContainer').children.length")
    print("chat children after 3s wait:", msgs)
    parts = page.evaluate("() => document.getElementById('participantsList').children.length")
    print("participants listed:", parts)

    # capture >=400 responses
    print("\n=== HTTP >=400 responses ===")
    for m in console_msgs:
        if "404" in m or "500" in m:
            pass
    for r in page._implobj._browser_context.pages if False else []:
        pass


    print("\n=== PAGE ERRORS ===")
    for e in page_errors: print(" ", e[:500])
    print("\n=== CONSOLE (errors/warnings) ===")
    for m in console_msgs:
        if m.startswith("[error") or m.startswith("[warning"): print(" ", m[:300])
    print("\n=== FAILED REQUESTS ===")
    for r in failed_reqs: print(" ", r[:300])
    browser.close()
