"""
Diagnose why the konferans room page "doesn't work" in a real browser.

Opens /konferans/room/<CODE> in headless Chromium (fake camera/mic), then
captures:
  - page errors (uncaught JS exceptions)
  - console warnings/errors
  - failed/blocked network requests
  - whether window.io / SimplePeer loaded
  - whether the Socket.IO client connected (socket.io handshake requests)
  - DOM state: video tiles, participants list, chat, waiting overlay
"""
import json
import sys
import time

from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:8080'
CODE = sys.argv[1] if len(sys.argv) > 1 else '4307MI'
NAME = sys.argv[2] if len(sys.argv) > 2 else 'Diag User'

page_errors = []
console_msgs = []
failed_requests = []
socketio_requests = []

with sync_playwright() as pw:
    browser = pw.chromium.launch(
        headless=True,
        args=['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'],
    )
    ctx = browser.new_context(permissions=['camera', 'microphone'])
    page = ctx.new_page()

    page.on('pageerror', lambda e: page_errors.append(str(e)))
    page.on('console', lambda m: console_msgs.append(f'[{m.type}] {m.text}') if m.type in ('error', 'warning') else None)
    page.on('requestfailed', lambda r: failed_requests.append(f'{r.method} {r.url} -> {r.failure}'))
    page.on('request', lambda r: socketio_requests.append(r.url) if '/socket.io/' in r.url else None)

    print(f'Opening {BASE}/konferans/room/{CODE}?user_name={NAME} ...')
    try:
        resp = page.goto(f'{BASE}/konferans/room/{CODE}?user_name={NAME}', wait_until='networkidle', timeout=30000)
        print(f'HTTP status: {resp.status}')
    except Exception as e:
        print(f'goto failed/timeout: {e}')

    # Give the socket time to connect and join
    time.sleep(6)

    state = page.evaluate("""() => {
        const s = {
            ioDefined: typeof io !== 'undefined',
            simplePeerDefined: typeof SimplePeer !== 'undefined',
            socketConnected: false,
            videoTiles: document.querySelectorAll('#videoContainer .konf-video-item, #videoContainer video, #videoContainer > div').length,
            participants: Array.from(document.querySelectorAll('#participantsList li, #participantsList .konf-participant')).map(li => li.textContent.trim()).slice(0, 12),
            chatMsgs: document.querySelectorAll('#chatContainer .chat-message, #chatContainer .konf-chat-msg, #chatMessages > div').length,
            waitingOverlayVisible: (() => { const el = document.getElementById('waitingOverlay'); return el ? el.style.display !== 'none' : false; })(),
            chatInputDisabled: (() => { const el = document.getElementById('chatInput'); return el ? el.disabled : null; })(),
            bodyClasses: document.body.className,
        };
        return s;
    }""")

    # extra: is there a global socket object we can inspect?
    sock_state = page.evaluate("""() => {
        try {
            // room.html keeps socket in closure; check via engine on window if exposed
            const hasEngine = !!(window.io && window.io.engine);
            return { hasEngine };
        } catch (e) { return { err: String(e) }; }
    }""")

    print()
    print('=== PAGE ERRORS (uncaught) ===')
    print('\n'.join(page_errors) if page_errors else '(none)')
    print()
    print('=== CONSOLE error/warning ===')
    print('\n'.join(console_msgs[:30]) if console_msgs else '(none)')
    print()
    print('=== FAILED REQUESTS ===')
    print('\n'.join(failed_requests) if failed_requests else '(none)')
    print()
    print('=== SOCKET.IO REQUESTS ===')
    print('\n'.join(socketio_requests[:10]) if socketio_requests else '(NONE — client never tried to connect!)')
    print()
    print('=== PAGE STATE ===')
    print(json.dumps(state, indent=2, ensure_ascii=False))
    print('sock probe:', sock_state)

    page.screenshot(path='_diag_room_state.png', full_page=False)
    print('\nScreenshot saved: _diag_room_state.png')

    browser.close()
