"""
E2E: two real browser participants in a konferans room.

Verifies the core conference loop end-to-end against the live dev server:
  E-1  Alice joins -> local video tile appears
  E-2  Bob joins -> BOTH see 2 video tiles (WebRTC negotiated via server signaling)
  E-3  participants lists update on both sides
  E-4  Bob sends chat -> Alice receives it (socket round-trip)
  E-5  Alice leaves -> Bob's tile count drops back to 1 (user_left + sid fix)
  E-0  no uncaught page errors on either side the whole time
"""
import sys
import time

from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:8080'
CODE = sys.argv[1] if len(sys.argv) > 1 else '4307MI'

fails = []
errors_a, errors_b = [], []


def check(name, cond):
    print(('  [OK]  ' if cond else '  [FAIL] ') + name)
    if not cond:
        fails.append(name)


def tiles(page):
    return page.evaluate("document.querySelectorAll('#videoContainer .konf-video-wrapper').length")


def names(page):
    return page.evaluate("Array.from(document.querySelectorAll('#participantsList .konf-participant-name')).map(e => e.textContent.trim())")


with sync_playwright() as pw:
    browser = pw.chromium.launch(
        headless=True,
        args=['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream',
              '--autoplay-policy=no-user-gesture-required'],
    )
    ctxA = browser.new_context(permissions=['camera', 'microphone'])
    ctxB = browser.new_context(permissions=['camera', 'microphone'])
    alice = ctxA.new_page()
    bob = ctxB.new_page()
    alice.on('pageerror', lambda e: errors_a.append(str(e)))
    bob.on('pageerror', lambda e: errors_b.append(str(e)))

    print(f'Alice joins {BASE}/konferans/room/{CODE} ...')
    alice.goto(f'{BASE}/konferans/room/{CODE}?user_name=Alice', wait_until='domcontentloaded')
    try:
        alice.wait_for_function(
            "document.querySelectorAll('#videoContainer .konf-video-wrapper').length >= 1",
            timeout=20000)
        check('E-1 Alice local video tile appears', True)
    except Exception as e:
        check(f'E-1 Alice local video tile appears ({e})', False)

    print('Bob joins ...')
    bob.goto(f'{BASE}/konferans/room/{CODE}?user_name=Bob', wait_until='domcontentloaded')

    # E-2: both sides negotiate a peer connection -> 2 tiles each
    for who, page in (('Alice', alice), ('Bob', bob)):
        try:
            page.wait_for_function(
                "document.querySelectorAll('#videoContainer .konf-video-wrapper').length >= 2",
                timeout=25000)
            check(f'E-2 {who} sees 2 video tiles (WebRTC OK)', True)
        except Exception as e:
            check(f'E-2 {who} sees 2 video tiles ({e})', False)

    # give participants_info a moment
    time.sleep(3)

    # E-3: participants lists
    n_a, n_b = names(alice), names(bob)
    check(f'E-3 Alice participants include Bob {n_a}', any('Bob' in n for n in n_a))
    check(f'E-3 Bob participants include Alice {n_b}', any('Alice' in n for n in n_b))

    # E-4: chat Bob -> Alice
    bob.fill('#chatInput', 'BONJOU ALICE E2E')
    bob.click('#sendChat')
    try:
        alice.wait_for_function(
            "Array.from(document.querySelectorAll('.konf-chat-bubble')).some(b => b.textContent.includes('BONJOU ALICE E2E'))",
            timeout=15000)
        check('E-4 chat Bob -> Alice delivered', True)
    except Exception as e:
        check(f'E-4 chat Bob -> Alice delivered ({e})', False)

    # E-5: Alice leaves -> Bob back to 1 tile
    alice.close()
    try:
        bob.wait_for_function(
            "document.querySelectorAll('#videoContainer .konf-video-wrapper').length <= 1",
            timeout=25000)
        check('E-5 Alice departure removes her tile on Bob side', True)
    except Exception as e:
        check(f'E-5 Alice departure removes her tile ({e})', False)

    bob.screenshot(path='_diag_room_bob_after.png')

    check('E-0 no uncaught JS errors on Alice page', not errors_a)
    if errors_a:
        print('    Alice errors:', errors_a[:5])
    check('E-0 no uncaught JS errors on Bob page', not errors_b)
    if errors_b:
        print('    Bob errors:', errors_b[:5])

    browser.close()

print()
if fails:
    print(f'{len(fails)} FAILURES: {fails}')
    sys.exit(1)
print('KONFERANS E2E (2 participants) PASSED')
