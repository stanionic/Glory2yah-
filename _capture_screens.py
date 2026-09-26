"""
Glory2YahPub — Automatic Screenshot Capture via Playwright
Captures real app screens across mobile/tablet/desktop for all key parcours.
Uses demo accounts ONLY (no sensitive data).
"""
import os, time, json
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8080"
OUT = "video_production/screenshots"
os.makedirs(f"{OUT}/mobile", exist_ok=True)
os.makedirs(f"{OUT}/tablet", exist_ok=True)
os.makedirs(f"{OUT}/desktop", exist_ok=True)

# ---- Demo accounts (from seed + app bootstrap) ----
SELLER = {"identifier": "+50937000001", "password": "demo123", "pseudo": "DemoShop"}
ADMIN = {"identifier": "Admin509", "password": "StanGlory2YahPub1986"}
STAN = {"identifier": "StanD", "password": "pass123"}

def login(page, account):
    page.goto(BASE + "/auth/login", wait_until="networkidle")
    page.fill("input[name='identifier']", account["identifier"])
    page.fill("input[name='password']", account["password"])
    page.click("button[type='submit'], form button, input[type='submit']")
    page.wait_for_timeout(2500)

def smart_shot(page, name, device="mobile"):
    # wait for network quiet + fonts
    page.wait_for_timeout(1200)
    page.screenshot(path=f"{OUT}/{device}/{name}.png", full_page=False)
    print(f"  [{device}] {name}.png")

def main():
    with sync_playwright() as p:
        # ================= MOBILE (iPhone-ish 390x844) =================
        print(">>> MOBILE CAPTURE")
        mob = p.chromium.launch()
        mc = mob.new_context(viewport={"width": 390, "height": 844},
                             device_scale_factor=2, is_mobile=True, has_touch=True)
        page = mc.new_page()

        # Homepage (logged out)
        page.goto(BASE + "/", wait_until="networkidle")
        smart_shot(page, "home_loggedout", "mobile")

        # Login as seller
        login(page, SELLER)
        smart_shot(page, "home_loggedin", "mobile")

        # Profile
        page.goto(BASE + "/auth/profile", wait_until="networkidle")
        smart_shot(page, "profile", "mobile")

        # My ads
        page.goto(BASE + "/auth/ads", wait_until="networkidle")
        # may error if product not listed; safe
        smart_shot(page, "my_ads", "mobile")

        # Submit ad (create post)
        page.goto(BASE + "/submit_ad", wait_until="networkidle")
        smart_shot(page, "submit_ad", "mobile")

        # Marketplace
        page.goto(BASE + "/mache/", wait_until="networkidle")
        smart_shot(page, "marketplace", "mobile")

        # Product detail (first sell ad)
        try:
            page.goto(BASE + "/ad/DEMO-SELL-001", wait_until="networkidle")
            smart_shot(page, "product_detail", "mobile")
        except Exception as e:
            print("  product detail skip:", e)

        # Cart
        try:
            page.goto(BASE + "/cart/add/DEMO-SELL-001", wait_until="networkidle")
            page.wait_for_timeout(800)
        except Exception as e:
            print("  cart add skip:", e)
        page.goto(BASE + "/cart/", wait_until="networkidle")
        smart_shot(page, "cart", "mobile")

        # Checkout
        page.goto(BASE + "/cart/checkout", wait_until="networkidle")
        smart_shot(page, "checkout", "mobile")

        # Gkach wallet
        page.goto(BASE + "/gkach/wallet", wait_until="networkidle")
        smart_shot(page, "gkach_wallet", "mobile")

        # Gkach transfer
        page.goto(BASE + "/gkach/transfer", wait_until="networkidle")
        smart_shot(page, "gkach_transfer", "mobile")

        # Gade TV
        page.goto(BASE + "/gadematch", wait_until="networkidle")
        smart_shot(page, "gade_tv", "mobile")

        # Services menu
        page.goto(BASE + "/", wait_until="networkidle")
        try:
            page.click(".nav-services, button[onclick*='toggleServicesMenu']")
            page.wait_for_timeout(800)
            smart_shot(page, "services_menu", "mobile")
        except Exception as e:
            print("  services menu skip:", e)

        # Bank
        page.goto(BASE + "/bank/", wait_until="networkidle")
        smart_shot(page, "bank", "mobile")

        mc.close()

        # ================= TABLET (768x1024) =================
        print(">>> TABLET CAPTURE")
        tab = p.chromium.launch()
        tc = tab.new_context(viewport={"width": 768, "height": 1024},
                             device_scale_factor=2, is_mobile=True, has_touch=True)
        page = tc.new_page()
        login(page, SELLER)
        page.goto(BASE + "/", wait_until="networkidle")
        smart_shot(page, "home", "tablet")
        page.goto(BASE + "/mache/", wait_until="networkidle")
        smart_shot(page, "marketplace", "tablet")
        page.goto(BASE + "/mache/categories", wait_until="networkidle")
        smart_shot(page, "categories", "tablet")
        tc.close()

        # ================= DESKTOP (1920x1080) =================
        print(">>> DESKTOP CAPTURE")
        desk = p.chromium.launch()
        dc = desk.new_context(viewport={"width": 1920, "height": 1080},
                              device_scale_factor=1)
        page = dc.new_page()
        # Homepage logged out
        page.goto(BASE + "/", wait_until="networkidle")
        smart_shot(page, "home", "desktop")
        # Marketplace
        page.goto(BASE + "/mache/", wait_until="networkidle")
        smart_shot(page, "marketplace", "desktop")
        # Admin login
        page.goto(BASE + "/admin/login", wait_until="networkidle")
        smart_shot(page, "admin_login", "desktop")
        # Login admin
        login(page, ADMIN)
        page.goto(BASE + "/admin/", wait_until="networkidle")
        smart_shot(page, "admin_dashboard", "desktop")
        # Admin users
        page.goto(BASE + "/admin/users", wait_until="networkidle")
        smart_shot(page, "admin_users", "desktop")
        # Admin gkach
        page.goto(BASE + "/admin/gkach/manage", wait_until="networkidle")
        smart_shot(page, "admin_gkach", "desktop")
        dc.close()

        print("ALL CAPTURES DONE")

if __name__ == "__main__":
    main()
