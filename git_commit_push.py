#!/usr/bin/env python3
"""
Glory2YahPub - Git Commit & Push Helper
----------------------------------------
This script does:
  1. Check git status, current branch, remote
  2. Ensure branch is 'main' (create if missing)
  3. Set remote origin to https://github.com/stanionic/Glory2yah-.git
  4. Stage ALL changes
  5. Create a descriptive commit (if any changes staged)
  6. Push to origin main with --set-upstream
  7. Print final status and remote URL
"""
import subprocess
import sys
import os
import datetime

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
TARGET_BRANCH = "main"
REMOTE_NAME = "origin"
REMOTE_URL = "https://github.com/stanionic/Glory2yah-.git"
LOG_FILE = os.path.join(REPO_DIR, "git_commit_push.log")

COMMIT_MSG = r"""Update UI modernization, session persistence, admin CRUD, clean start scripts

## 🔧 BUG FIXES
- Fix ecole_biblique base.html: remove stray 'CREA' text before <!DOCTYPE html>
- Fix admin 405 Method Not Allowed: add missing 6 CRUD routes
  * POST /admin/ads/update (update ad status)
  * POST /admin/ads/delete/<ad_id> (admin-only ad delete)
  * POST /admin/batches/delete/<batch_id>
  * GET/POST /admin/batches/edit/<batch_id>
  * POST /admin/batches/<batch_id>/add-ad
  * POST /admin/batches/<batch_id>/remove-ad/<ad_id>
- Fix admin CSRF: add {{ csrf_token() }} to ALL POST forms in admin.html + admin_edit_batch.html
- Fix auth CSRF bug: change {{ csrf_token }} -> {{ csrf_token() }} in:
  * templates/auth/profile.html
  * templates/auth/edit_profile.html

## 🔐 SESSION PERSISTENCE FIX
Users were forced to re-register every visit. Root causes + fixes:
- No permanent session flag (default session-only cookie)
  * Register: auto-login user immediately -> redirects to / NOT /auth/login
  * Login/Register: default remember=True + session.permanent=True always
  * PERMANENT_SESSION_LIFETIME = 30 days, REFRESH_EACH_REQUEST=True
  * Custom cookie glory2yah_session (HttpOnly, SameSite=Lax, 30 days)
  * Custom cookie glory2yah_remember (365 days, REFRESH_EACH_REQUEST=True)
- login_manager.session_protection = None (no logout on IP/UA change; common on mobile)
- user_loader wrapped with try/except + is_active check
- Login template "Sonje mwen" checkbox is now CHECKED by default (1 ane)

## 🎨 MODERN REACT-LIKE CSS (ADDITIVE ONLY — NO g2y CSS BROKEN)
Added ~1500 lines of new component CSS to static/css/style.css ON TOP of
existing standard g2y variables.css + g2y-app.css (preserved 100%):
- Forms (.form-group, .form-label, .form-control, .form-select, .form-hint, .form-error, dashed file dropzones) with focus-rings, is-invalid/is-valid states
- Cards (.card, .card-header, .card-title, .card-body, .card-footer) with hover-lift transform animations
- Badges (.badge-*) and Tags: 6 color variants (primary/success/danger/warning/info/gold, pill-style)
- Skeleton loading states (.skeleton, .skeleton-text, .skeleton-heading, .skeleton-image, .skeleton-avatar, .skeleton-card) with shimmer keyframe animation
- Empty states (.empty-state, .empty-state-icon, .empty-state-title, .empty-state-description, .empty-state-actions)
- Modern button system: .btn-primary/.btn-secondary/.btn-outline/.btn-success/.btn-danger/.btn-purple + sizes sm/lg/block/icon-only + scale(0.97) press animation + disabled states
- Responsive tables (.table-container + .table with sticky headers + mobile label-value mode)
- Progress bars with gradient color variants + .progress-label
- Dropdowns, Pagination (pill buttons, active gradient), Tabs (segmented, scrollable mobile), Accordions (max-height collapse transitions), List groups, Tooltips (data-tooltip)
- Toast notifications (top-right fixed, 4 color variants with left accent border, slide-in + fade-out animations)
- Stat/KPI cards (.stat-card with top accent border, .stat-card-icon, .stat-card-change positive/negative)
- Modals (.modal-backdrop blur, .modal-container with scale-in animation, header/body/footer)
- Avatars (.avatar-xs/sm/md/lg/xl + .avatar-ring + overlapping .avatar-group)
- Custom checkboxes/radios (hidden native input, styled custom box with checkmark/dot)
- Switch toggle sliders
- FULL dark mode support for ALL new components
  * Automatic via prefers-color-scheme: dark
  * Manual via .dark-mode body class
- Mobile responsive breakpoints (1024px / 640px / 480px / 375px)
- Grid utility classes: .grid-cols-1 / 2 / 3 / 4 with responsive breakpoints

All existing g2y CSS components (header, bottom-nav, stories, services popup,
ad cards, hero, carousel, mobile TikTok scroll hide/show) are untouched.

## 🎯 AUTH TEMPLATES PRESERVED (already looked great)
- register.html, login.html, forgot_password.html, profile.html, edit_profile.html
Already have React-like glass-morphism gradient cards, animations, focus-rings.
Kept as-is, no modifications except CSRF token function call fixes on profile/edit_profile.

## 🛒 GKACH + CART TEMPLATES PRESERVED (already looked good)
- gkach/wallet.html, request.html, transfer.html
- cart/index.html, checkout.html, cart_success.html, etc.
Already have bespoke custom modern styling. Left untouched.

## 🧹 START SCRIPT CLEANUP
Deleted 12 duplicate/unused launcher/start/test-start Python scripts,
leaving ONLY simple_start.py as THE single official working launcher.

Removed:
- start.py / run.py / run_app.py / run_server.py / start_debug.py
- test_startup.py / diagnose.py
- test_imports.py / test_app_import.py / test_full_imports.py
- _fetch_page.py / debug_redirect.py

Preserved (not start scripts — data setup / test creation / verification kept):
- create_*.py / seed_*.py / assign_ads_to_user.py
- setup_*.py (stand_user, postgres, admin)
- check_*.py / verify_*.py / inspect_ads.py / import_images.py
- debug_konferans*.py / debug_ecole.py / test_ecole.py / test_blueprints.py
  test_ads_donation_flow.py / test_konferans_fix.py / create_teacher_and_test.py
- fix_test_user.py / update_user_name.py / delete_test_ads.py
- PLUS: start_server.cmd (double-clickable Windows helper)

One launcher to rule them all:  py -3 simple_start.py
Server: http://127.0.0.1:8080/
"""

def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run(cmd_list, check=True, allow_error=False):
    log(f"▶ RUN: {' '.join(cmd_list)}")
    try:
        result = subprocess.run(
            cmd_list,
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        if result.stdout.strip():
            for l in result.stdout.strip().splitlines():
                log(f"  STDOUT: {l}")
        if result.stderr.strip():
            for l in result.stderr.strip().splitlines():
                log(f"  STDERR: {l}")
        log(f"  EXIT CODE: {result.returncode}")
        if check and result.returncode != 0 and not allow_error:
            log("❌ COMMAND FAILED — aborting.")
            sys.exit(result.returncode)
        return result
    except FileNotFoundError as e:
        log(f"❌ EXECUTABLE NOT FOUND: {cmd_list[0]} — {e}")
        sys.exit(2)


def main():
    log("=" * 70)
    log("GLORY2YAHPUB — GIT COMMIT + PUSH HELPER")
    log("=" * 70)

    # 1. Check git exists
    run(["git", "--version"])

    # 2. Check repo state
    log("--- Current status ---")
    run(["git", "--no-pager", "status", "--short"])

    log("--- Current branch ---")
    res = run(["git", "branch", "--show-current"])
    current_branch = (res.stdout or "").strip()
    log(f"  -> Current branch is: '{current_branch}'")

    # 3. Ensure main branch exists and we are on it
    if current_branch == TARGET_BRANCH:
        log(f"✅ Already on branch '{TARGET_BRANCH}'")
    else:
        log(f"🔀 Not on '{TARGET_BRANCH}'. Attempting to switch/create...")
        # Try switch to existing main
        r = run(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{TARGET_BRANCH}"],
                check=False, allow_error=True)
        if r.returncode == 0:
            run(["git", "switch", TARGET_BRANCH])
        else:
            log(f"Branch {TARGET_BRANCH} doesn't exist — creating from current.")
            run(["git", "checkout", "-b", TARGET_BRANCH])

    # 4. Set / update remote origin
    log("--- Setting remote origin ---")
    r = run(["git", "remote", "get-url", REMOTE_NAME], check=False, allow_error=True)
    if r.returncode == 0:
        current_url = (r.stdout or "").strip()
        log(f"  existing origin URL: {current_url}")
        if current_url != REMOTE_URL:
            log(f"  -> updating to: {REMOTE_URL}")
            run(["git", "remote", "set-url", REMOTE_NAME, REMOTE_URL])
        else:
            log("  -> already correct, skipping update.")
    else:
        log(f"  origin missing — adding: {REMOTE_URL}")
        run(["git", "remote", "add", REMOTE_NAME, REMOTE_URL])
    run(["git", "remote", "-v"])

    # 5. Stage ALL changes
    log("--- Staging all changes ---")
    run(["git", "add", "-A"])
    run(["git", "--no-pager", "status", "--short"])

    # 6. Check if anything is staged for commit
    r = run(["git", "diff", "--cached", "--quiet"], check=False, allow_error=True)
    if r.returncode == 0:
        log("⚠️  NOTHING STAGED — no changes to commit. Aborting commit (still will try push if ahead).")
        commit_done = False
    else:
        log("--- Creating commit ---")
        run(["git", "commit", "-m", COMMIT_MSG])
        commit_done = True

    # 7. Push
    log("--- Pushing to origin main ---")
    run(["git", "push", "-u", REMOTE_NAME, TARGET_BRANCH], check=False, allow_error=False)

    log("=" * 70)
    log("✅ FINAL STATUS")
    log("=" * 70)
    run(["git", "--no-pager", "status", "--short"])
    run(["git", "log", "--oneline", "-3"])
    log(f"🌐 GitHub repo: {REMOTE_URL}")
    log("=" * 70)
    log("DONE ✅")
    sys.exit(0)


if __name__ == "__main__":
    main()
