import sys
try:
    from playwright.sync_api import sync_playwright
    p = sync_playwright().start()
    b = p.chromium.launch()
    page = b.new_page()
    page.set_content("<h1>test</h1>")
    page.screenshot(path="video_production/_pw_test.png")
    b.close()
    p.stop()
    print("PLAYWRIGHT_OK")
except Exception as e:
    print("PLAYWRIGHT_FAIL:", type(e).__name__, str(e))
    sys.exit(1)
