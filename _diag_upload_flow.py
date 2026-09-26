"""Drive the real konferans media-upload flow as the room owner.

Logs in, opens the owned room, picks a file with the real <input type=file>,
watches /konferans/upload_media, clicks "Afiche nan ekran prensipal", then
checks that the resulting media URL actually serves and renders.
"""
import json
import pathlib
from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:5000'
ROOM = 'DIAG02'

# small valid PNG
PNG = bytes.fromhex(
    '89504e470d0a1a0a0000000d49484452000000200000002008060000'
    '00737a7af40000001f49444154484botimes'.replace('otimes', '')
)


def make_fixture():
    """Write a real PNG to disk with Pillow if available, else a 1x1 raw PNG."""
    p = pathlib.Path('_diag_fixture.png')
    try:
        from PIL import Image
        Image.new('RGB', (640, 360), (30, 90, 200)).save(p)
    except Exception:
        p.write_bytes(bytes.fromhex(
            '89504e470d0a1a0a0000000d494844520000000100000001080600000'
            '01f15c4890000000a49444154789c6300010000050001'
            '0d0a2db40000000049454e44ae426082'))
    return p


def main():
    fixture = make_fixture()
    print('fixture:', fixture, fixture.stat().st_size, 'bytes')

    with sync_playwright() as p:
        browser = p.chromium.launch(args=[
            '--use-fake-ui-for-media-stream',
            '--use-fake-device-for-media-stream',
            '--autoplay-policy=no-user-gesture-required',
        ])
        ctx = browser.new_context(viewport={'width': 1280, 'height': 800},
                                  permissions=['camera', 'microphone'])
        page = ctx.new_page()
        page.on('pageerror', lambda e: print('  pageerror:', e))
        page.on('console', lambda m: print(f'  console.{m.type}: {m.text}')
                if m.type in ('error', 'warning') else None)

        # log the network for anything media-ish
        net = []
        page.on('response', lambda r: net.append((r.status, r.url))
                if ('upload_media' in r.url or 'uploads/konferans' in r.url) else None)

        # --- login with the real form ---
        page.goto(f'{BASE}/auth/login', wait_until='domcontentloaded')
        page.fill('#identifier', 'diaguser')
        page.fill('input[name="password"]', 'DiagPass123!')
        page.click('button[type="submit"]')
        page.wait_for_load_state('domcontentloaded')
        page.wait_for_timeout(1000)
        print('after login ->', page.url)
        if '/auth/login' in page.url:
            print('LOGIN FAILED:', page.inner_text('body')[:400])
            return

        # --- open the owned room ---
        page.goto(f'{BASE}/konferans/room/{ROOM}?user_name=Diag%20User',
                  wait_until='domcontentloaded')
        page.wait_for_timeout(3500)
        print('room ->', page.url)
        print('owner controls present:',
              page.evaluate("() => !!document.getElementById('mediaFileInput')"))

        # --- upload through the real file input ---
        page.set_input_files('#mediaFileInput', str(fixture))
        page.wait_for_timeout(4000)

        print('\n=== upload network ===')
        for status, url in net:
            print(f'  {status}  {url}')

        dialog = page.evaluate("""() => {
            const d = document.querySelector('.konf-media-dialog');
            if (!d) return null;
            const prev = document.getElementById('mediaDialogPreview');
            const img = prev.querySelector('img, video, audio');
            return {
                open: true,
                previewTag: img ? img.tagName : null,
                previewSrc: img ? img.getAttribute('src') : null,
                previewNaturalW: img && img.naturalWidth !== undefined ? img.naturalWidth : null,
                previewComplete: img && img.complete !== undefined ? img.complete : null,
            };
        }""")
        print('\n=== share dialog ===')
        print(json.dumps(dialog, indent=2))
        if not dialog:
            print('NO DIALOG -> upload failed; body toast:',
                  page.inner_text('body')[:300])
            page.screenshot(path='_diag_upload_flow.png')
            return

        # --- click "show on main screen" ---
        page.click('#mediaShareMain')
        page.wait_for_timeout(2500)

        res = page.evaluate("""() => {
            const d = document.getElementById('mediaDisplay');
            const r = d.getBoundingClientRect();
            const el = document.getElementById('mediaDisplayContent').firstElementChild;
            const er = el ? el.getBoundingClientRect() : null;
            return {
                classes: d.className,
                rect: [r.x, r.y, r.width, r.height],
                coversViewport: r.x === 0 && r.y === 0 &&
                    r.width === window.innerWidth && r.height === window.innerHeight,
                mediaTag: el ? el.tagName : null,
                mediaSrc: el ? el.getAttribute('src') : null,
                naturalW: el && el.naturalWidth !== undefined ? el.naturalWidth : null,
                naturalH: el && el.naturalHeight !== undefined ? el.naturalHeight : null,
                complete: el && el.complete !== undefined ? el.complete : null,
                rendered: er ? [er.width, er.height] : null,
                title: document.getElementById('mediaDisplayTitle').textContent,
            };
        }""")
        print('\n=== main screen after share ===')
        print(json.dumps(res, indent=2))

        if res['mediaSrc']:
            r = page.request.get(BASE + res['mediaSrc'])
            print(f"\nGET {res['mediaSrc']} -> {r.status} "
                  f"{r.headers.get('content-type')} {len(r.body())} bytes")

        print('\n=== full network ===')
        for status, url in net:
            print(f'  {status}  {url}')

        page.screenshot(path='_diag_upload_flow.png')
        print('\nscreenshot -> _diag_upload_flow.png')
        browser.close()


if __name__ == '__main__':
    main()
