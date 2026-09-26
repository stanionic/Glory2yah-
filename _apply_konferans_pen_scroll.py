"""Apply the Konferans "media scroll-bar + pen live editing" upgrade.

Why a script: templates/konferans/room.html is ~190 KB, so the IDE editor
tool times out on it. This script applies every change with exact anchors,
aborts on the first mismatch, and keeps the original CRLF line endings.

Files touched:
  * templates/konferans/room.html   (media viewport markup + JS)
  * static/css/konferans.css        (scroll bars, zoom label, stage)
  * konferans/routes.py             (media_view / media_annotation_remove relays)
"""
import io
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
ROOM = os.path.join(ROOT, 'templates', 'konferans', 'room.html')
CSS = os.path.join(ROOT, 'static', 'css', 'konferans.css')
ROUTES = os.path.join(ROOT, 'konferans', 'routes.py')
BACKUP_DIR = os.path.join(ROOT, '.dbg', 'pen_scroll_backup')


def read(path):
    with io.open(path, 'r', encoding='utf-8', newline='') as fh:
        return fh.read()


def write(path, text):
    d = os.path.dirname(path)
    if not os.path.isdir(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
    shutil.copy2(path, os.path.join(BACKUP_DIR, os.path.basename(path) + '.bak'))
    with io.open(path, 'w', encoding='utf-8', newline='') as fh:
        fh.write(text)


def apply(text, old, new, label, style):
    old_s = old.replace('\n', style) if style else old
    new_s = new.replace('\n', style) if style else new
    count = text.count(old_s)
    if count != 1:
        raise SystemExit('ANCHOR FAIL [%s]: %d occurrence(s) (expected 1)' % (label, count))
    print('  [OK]   %s' % label)
    return text.replace(old_s, new_s)


def replace_region(text, start_marker, end_marker, new, label, style):
    s = start_marker.replace('\n', style) if style else start_marker
    e = end_marker.replace('\n', style) if style else end_marker
    i = text.find(s)
    if i < 0:
        raise SystemExit('REGION FAIL [%s]: start marker not found' % label)
    j = text.find(e, i)
    if j < 0:
        raise SystemExit('REGION FAIL [%s]: end marker not found' % label)
    j += len(e)
    print('  [OK]   %s (replaced %d chars)' % (label, j - i))
    return text[:i] + new.replace('\n', style) + text[j:]


# ---------------------------------------------------------------------------
# 1) room.html — media display header: zoom + page-scroll + view-sync buttons
# ---------------------------------------------------------------------------
ROOM_HEADER_OLD = r'''                        <button class="konf-media-ctrl-btn" id="mediaPenBtn" onclick="togglePenTool()" title="Aktive/Dezaktive Stylos anotasyon"><i class="fas fa-pen"></i></button>'''
ROOM_HEADER_NEW = r'''                        <button class="konf-media-ctrl-btn" id="mediaPenBtn" onclick="togglePenTool()" title="Aktive/Dezaktive zouti edisyon (stylos, flambo, kadran, flèch, gom)"><i class="fas fa-pen"></i></button>
                        <button class="konf-media-ctrl-btn" id="mediaViewSyncBtn" onclick="toggleMediaViewSync()" title="Swiv: elèv yo wè menm zoum ak menm pozisyon ak ou"><i class="fas fa-satellite-dish"></i></button>
                        {% endif %}
                        {# Zoum + defilman (scroll) disponib pou tout moun — se yon vi lokal #}
                        {# Stylos/syiv rete pou mèt sal la sèlman (blòk anwo a) #}
                        <button class="konf-media-ctrl-btn" id="mediaScrollUpBtn" onclick="scrollMediaPage(-1)" title="Defile anwo (paj anwo) — PageUp"><i class="fas fa-angle-double-up"></i></button>
                        <button class="konf-media-ctrl-btn" id="mediaScrollDownBtn" onclick="scrollMediaPage(1)" title="Defile anba (paj anba) — PageDown"><i class="fas fa-angle-double-down"></i></button>
                        <button class="konf-media-ctrl-btn" id="mediaZoomOutBtn" onclick="zoomMedia(-1)" title="Zoum mwens (-)"><i class="fas fa-search-minus"></i></button>
                        <span class="konf-media-zoom-label" id="mediaZoomLabel" onclick="resetMediaZoom()" title="Klike pou tounen nan mòd Ajiste (0)">Ajiste</span>
                        <button class="konf-media-ctrl-btn" id="mediaZoomInBtn" onclick="zoomMedia(1)" title="Zoum plis — agrandi pou li pi byen (+)"><i class="fas fa-search-plus"></i></button>
                        {% if is_owner %}'''


# ---------------------------------------------------------------------------
# 2) room.html — annotation toolbar: eraser tool + export annotated media
# ---------------------------------------------------------------------------
ROOM_TOOLBAR_OLD = r'''                    <button type="button" class="konf-ann-btn konf-ann-danger" id="annClearBtn" onclick="clearAnnotations()" title="Efase tout anotasyon"><i class="fas fa-eraser"></i></button>'''

ROOM_TOOLBAR_NEW = r'''                    <button type="button" class="konf-ann-btn" id="annEraserBtn" onclick="setAnnTool('eraser')" title="Gom (E) — klike oswa glise sou yon tras pou efase l"><i class="fas fa-eraser"></i> Gom</button>
                    <button type="button" class="konf-ann-btn konf-ann-danger" id="annClearBtn" onclick="clearAnnotations()" title="Efase tout anotasyon"><i class="fas fa-trash-alt"></i></button>
                    <button type="button" class="konf-ann-btn" id="annDownloadBtn" onclick="downloadAnnotatedMedia()" title="Telechaje medya a ak anotasyon yo (PNG)"><i class="fas fa-download"></i></button>'''


# ---------------------------------------------------------------------------
# 3) room.html — bump the CSS cache-buster (new styles are required)
# ---------------------------------------------------------------------------
ROOM_CSS_OLD = r'''<link rel="stylesheet" href="/static/css/konferans.css?v=6">'''
ROOM_CSS_NEW = r'''<link rel="stylesheet" href="/static/css/konferans.css?v=7">'''


# ---------------------------------------------------------------------------
# 4) room.html — showMediaInMain(): render inside the scrollable stage,
#    reset the strokes of the previous page and re-arm zoom/pen.
# ---------------------------------------------------------------------------
SHOW_START = r'''    function showMediaInMain(mediaData) {'''
SHOW_END = r'''        setTimeout(() => display.classList.remove('showing'), 450);
    }'''

SHOW_NEW = r'''    function showMediaInMain(mediaData) {
        const mediaUrl = getMediaUrl(mediaData);
        const display = document.getElementById('mediaDisplay');
        const stage = getMediaStage();
        const viewport = getMediaViewport();
        const title = document.getElementById('mediaDisplayTitle');
        const displayName = mediaData.user_name || userName;
        if (!display || !stage || !viewport || !title) return;

        // Reset state when showing new media
        display.classList.remove('minimized', 'fullscreen', 'position-up', 'position-down');
        mediaMinimized = false;
        mediaPosition = 'default';
        document.body.style.overflow = '';

        // Reset toggle button icon
        const toggleBtn = document.getElementById('mediaToggleBtn');
        if (toggleBtn) {
            toggleBtn.querySelector('i').className = 'fas fa-eye-slash';
            toggleBtn.title = 'Baryè medya a';
        }

        // Reset fullscreen button icon
        const fullscreenBtn = document.getElementById('mediaFullscreenBtn');
        if (fullscreenBtn) {
            fullscreenBtn.querySelector('i').className = 'fas fa-expand';
            fullscreenBtn.title = 'Ekran konplè';
        }

        title.textContent = `${mediaData.original_name || 'Medya'} — ${displayName}`;
        currentMediaName = mediaData.original_name || 'medya';
        currentMediaType = mediaData.media_type || '';

        // Strokes belong to the page that just left the screen — wipe them
        // everywhere so nobody keeps drawing on a ghost page.
        if (annStrokes.length) {
            annStrokes.length = 0;
            if (isOwner && typeof socket !== 'undefined' && socket) {
                socket.emit('media_annotation_clear', { room_id: roomId });
            }
        }

        stage.innerHTML = '';
        if (mediaData.media_type === 'image') {
            stage.innerHTML = `<img src="${mediaUrl}" alt="${escapeHtml(mediaData.original_name || 'Medya')}" draggable="false">`;
        } else if (mediaData.media_type === 'video') {
            stage.innerHTML = `<video src="${mediaUrl}" controls autoplay playsinline></video>`;
        } else if (mediaData.media_type === 'audio') {
            stage.innerHTML = `<div class="konf-media-audio-player"><i class="fas fa-music"></i><audio src="${mediaUrl}" controls autoplay></audio><span>${escapeHtml(mediaData.original_name || 'Medya')}</span></div>`;
        } else if (/\.pdf$/i.test(mediaData.original_name || '')) {
            stage.innerHTML = `<iframe src="${mediaUrl}" title="${escapeHtml(mediaData.original_name || 'PDF')}"></iframe>`;
        } else {
            stage.innerHTML = `<div class="konf-media-file-link"><i class="fas fa-file"></i> <a href="${mediaUrl}" target="_blank" rel="noopener">${escapeHtml(mediaData.original_name || 'Medya')}</a></div>`;
        }

        viewport.scrollTop = 0;
        viewport.scrollLeft = 0;
        display.style.display = 'block';
        display.style.order = '';
        display.classList.add('showing');
        setTimeout(() => display.classList.remove('showing'), 450);

        // Re-arm the scroll/zoom viewport and the pen layer for the new media
        attachMediaViewportEvents();
        const shown = getActiveMediaEl();
        if (shown && shown.tagName === 'IMG' && !(shown.complete && shown.naturalWidth)) {
            shown.addEventListener('load', () => {
                applyMediaZoom({ force: true });
                syncMediaPenLayer();
            }, { once: true });
        } else if (shown && shown.tagName === 'VIDEO') {
            shown.addEventListener('loadedmetadata', () => applyMediaZoom({ force: true }), { once: true });
        }
        applyMediaZoom({ force: true });
        syncMediaPenLayer();
    }
'''



# ---------------------------------------------------------------------------
# 5) room.html — clearMediaDisplay(): also reset the pen/zoom state
# ---------------------------------------------------------------------------
CLEAR_START = r'''    function clearMediaDisplay() {'''
CLEAR_END = r'''        display.classList.remove('fullscreen');
        document.body.style.overflow = '';
    }'''

CLEAR_NEW = r'''    function clearMediaDisplay() {
        const display = document.getElementById('mediaDisplay');
        const stage = getMediaStage();
        const viewport = getMediaViewport();
        if (!display) return;
        display.style.display = 'none';
        if (stage) stage.innerHTML = '';
        if (viewport) {
            viewport.scrollTop = 0;
            viewport.scrollLeft = 0;
        }
        // Drop the editing layer + zoom of the media that is leaving the screen
        penActive = false;
        annStrokes.length = 0;
        currentMediaName = '';
        currentMediaType = '';
        mediaZoomPercent = 0;
        lastZoomKey = '';
        const toolbar = document.getElementById('mediaAnnotationToolbar');
        if (toolbar) toolbar.style.display = 'none';
        syncAnnButtons();
        // Remove fullscreen mode if active
        display.classList.remove('fullscreen');
        document.body.style.overflow = '';
    }
'''


# ---------------------------------------------------------------------------
# 6) room.html — re-measure on fullscreen in/out
# ---------------------------------------------------------------------------
FS_EXIT_OLD = r'''            document.body.style.overflow = '';
            showToast('<i class="fas fa-compress"></i> Soti nan ekran konplè.', 'info', 2000);'''
FS_EXIT_NEW = r'''            document.body.style.overflow = '';
            requestAnimationFrame(() => applyMediaZoom({ force: true }));
            showToast('<i class="fas fa-compress"></i> Soti nan ekran konplè.', 'info', 2000);'''

FS_ENTER_OLD = r'''            document.body.style.overflow = 'hidden';
            showToast('<i class="fas fa-expand"></i> Ekran konplè aktive. Peze ESC pou soti.', 'info', 3000);'''
FS_ENTER_NEW = r'''            document.body.style.overflow = 'hidden';
            requestAnimationFrame(() => applyMediaZoom({ force: true }));
            showToast('<i class="fas fa-expand"></i> Ekran konplè aktive. Peze ESC pou soti.', 'info', 3000);'''



# ---------------------------------------------------------------------------
# 7) room.html — the whole media pen / annotation block is rebuilt:
#    * scroll viewport + zoom + live view sync helpers
#    * normalized (0..1) stroke coordinates => strokes stay glued to the media
#      whatever the screen size, the zoom level or the scroll position
#    * new eraser tool, annotated-media export, keyboard shortcuts
# ---------------------------------------------------------------------------
PEN_START = r'''    // ===== Media Pen / Annotation / Selection tool (Teacher / Owner only + broadcast) ====='''
PEN_END = r'''    socket.on('media_annotation_clear', () => {
        annStrokes.length = 0;
        redrawAnnotations();
    });'''

PEN_A = r'''
    // ===== Baryè defilman (scroll) + Zoum + Swiv an dirèk sou medya a =====
    // The teacher uploads a media, zooms it and scrolls it like a real
    // whiteboard. Every stroke is stored in normalized coordinates (0..1 of the
    // media box) so it stays glued to the document on every screen, zoom level
    // and scroll position — for the teacher AND for everybody watching live.
    const MEDIA_ZOOM_STEPS = [25, 50, 75, 100, 125, 150, 200, 300, 400];
    let mediaZoomPercent = 0;      // 0 = "Ajiste" (fits the viewport), else 25..400
    let mediaViewSync = true;      // owner pushes zoom + scroll to the whole room
    let currentMediaName = '';
    let currentMediaType = '';
    let lastZoomKey = '';
    let mediaScrollRaf = null;
    let mediaZoomRaf = null;

    function getMediaViewport() { return document.getElementById('mediaDisplayContent'); }
    function getMediaStage() { return document.getElementById('mediaStage'); }

    function getActiveMediaEl() {
        const stage = getMediaStage();
        if (!stage) return null;
        return stage.querySelector('img, video, iframe, .konf-media-audio-player, .konf-media-file-link');
    }

    function mediaNaturalSize(el) {
        if (!el) return { w: 0, h: 0 };
        if (el.tagName === 'IMG') return { w: el.naturalWidth || 0, h: el.naturalHeight || 0 };
        if (el.tagName === 'VIDEO') return { w: el.videoWidth || 0, h: el.videoHeight || 0 };
        return { w: 0, h: 0 };
    }

    function mediaScrollFraction() {
        const vp = getMediaViewport();
        if (!vp) return { fx: 0, fy: 0 };
        const maxX = vp.scrollWidth - vp.clientWidth;
        const maxY = vp.scrollHeight - vp.clientHeight;
        return {
            fx: maxX > 2 ? vp.scrollLeft / maxX : 0,
            fy: maxY > 2 ? vp.scrollTop / maxY : 0
        };
    }

    function restoreMediaScrollFraction(frac) {
        const vp = getMediaViewport();
        if (!vp || !frac) return;
        const maxX = Math.max(0, vp.scrollWidth - vp.clientWidth);
        const maxY = Math.max(0, vp.scrollHeight - vp.clientHeight);
        vp.scrollLeft = Math.round((frac.fx || 0) * maxX);
        vp.scrollTop = Math.round((frac.fy || 0) * maxY);
    }'''


PEN_B = r'''

    // Sizing is done in JS (not only in CSS) so the scroll container always
    // knows the real rendered size of the media: that is what makes the scroll
    // bars appear on a tall scanned page, and disappear again in Ajiste mode.
    function applyMediaZoom(opts) {
        opts = opts || {};
        const vp = getMediaViewport();
        const stage = getMediaStage();
        if (!vp || !stage) return;
        const media = getActiveMediaEl();
        const label = document.getElementById('mediaZoomLabel');
        const availW = Math.max(160, (vp.clientWidth || 320) - 32);
        const availH = Math.max(160, (vp.clientHeight || 320) - 32);
        const nat = mediaNaturalSize(media);
        const key = [vp.offsetWidth, vp.offsetHeight, mediaZoomPercent,
                     currentMediaName, media ? media.tagName : '', nat.w, nat.h].join('|');
        if (!opts.force && key === lastZoomKey) {
            if (label) label.textContent = mediaZoomPercent === 0 ? 'Ajiste' : (mediaZoomPercent + '%');
            return;
        }
        lastZoomKey = key;
        const frac = opts.keepScroll === false ? { fx: 0, fy: 0 } : mediaScrollFraction();
        if (media) {
            const tag = media.tagName;
            if (tag === 'IFRAME') {
                const pct = mediaZoomPercent === 0 ? 1 : mediaZoomPercent / 100;
                media.style.width = Math.round(availW * pct) + 'px';
                media.style.height = Math.round(Math.max(360, availH * pct)) + 'px';
            } else if (tag === 'IMG' || tag === 'VIDEO') {
                if (mediaZoomPercent === 0) {
                    if (nat.w && nat.h) {
                        const scale = Math.min(availW / nat.w, availH / nat.h, 1);
                        media.style.width = Math.max(1, Math.round(nat.w * scale)) + 'px';
                        media.style.height = Math.max(1, Math.round(nat.h * scale)) + 'px';
                    }
                } else {
                    media.style.width = Math.max(80, Math.round(availW * mediaZoomPercent / 100)) + 'px';
                    media.style.height = 'auto';
                }
            } else {
                media.style.width = '';
                media.style.height = '';
            }
        }
        if (label) {
            label.textContent = mediaZoomPercent === 0 ? 'Ajiste' : (mediaZoomPercent + '%');
            label.classList.toggle('active', mediaZoomPercent !== 0);
        }
        requestAnimationFrame(() => {
            restoreMediaScrollFraction(frac);
            resizeAnnotationCanvas();
        });
    }'''


PEN_C = r'''

    function setMediaZoom(percent, opts) {
        opts = opts || {};
        mediaZoomPercent = Math.max(0, Math.min(400, Math.round(Number(percent) || 0)));
        lastZoomKey = '';
        applyMediaZoom({ force: true, keepScroll: opts.keepScroll !== false });
        if (!opts.silent) emitMediaView();
        return mediaZoomPercent;
    }

    function zoomMedia(direction) {
        if (!getActiveMediaEl()) {
            showToast('<i class="fas fa-info-circle"></i> Pa gen medya sou ekran an pou zoum.', 'info', 2600);
            return;
        }
        const idx = MEDIA_ZOOM_STEPS.indexOf(mediaZoomPercent);
        let next;
        if (direction > 0) {
            next = (mediaZoomPercent === 0 || idx < 0) ? 100 : MEDIA_ZOOM_STEPS[Math.min(MEDIA_ZOOM_STEPS.length - 1, idx + 1)];
        } else {
            next = (mediaZoomPercent === 0 || idx < 0) ? 75 : (idx === 0 ? 0 : MEDIA_ZOOM_STEPS[idx - 1]);
        }
        setMediaZoom(next);
        showToast('<i class="fas fa-search-plus"></i> Zoum: <b>' + (next === 0 ? 'Ajiste' : next + '%') + '</b>', 'info', 1800);
    }

    function resetMediaZoom() {
        setMediaZoom(0);
        showToast('<i class="fas fa-compress-arrows-alt"></i> Medya tounen nan mòd <b>Ajiste</b>.', 'info', 1800);
    }

    function scrollMediaPage(direction) {
        const vp = getMediaViewport();
        if (!vp) return;
        const delta = Math.max(80, Math.round(vp.clientHeight * 0.85)) * (direction > 0 ? 1 : -1);
        if (typeof vp.scrollBy === 'function') vp.scrollBy({ top: delta, left: 0, behavior: 'smooth' });
        else vp.scrollTop += delta;
    }

    function toggleMediaViewSync() {
        mediaViewSync = !mediaViewSync;
        const btn = document.getElementById('mediaViewSyncBtn');
        if (btn) {
            btn.classList.toggle('active', mediaViewSync);
            btn.title = mediaViewSync
                ? 'Swiv aktif — elèv yo wè menm bagay ak ou'
                : 'Swiv dezaktive — klike pou aktive';
        }
        showToast(mediaViewSync
            ? '<i class="fas fa-satellite-dish"></i> Swiv aktif: elèv yo ap swiv zoum ak defilman w.'
            : '<i class="fas fa-satellite-dish"></i> Swiv dezaktive: chak moun kontwole pwòp vi li.', 'info', 2800);
        if (mediaViewSync) emitMediaView();
    }

    function emitMediaView() {
        if (!isOwner || !mediaViewSync) return;
        if (!getMediaViewport() || !getActiveMediaEl()) return;
        const frac = mediaScrollFraction();
        socket.emit('media_view', {
            room_id: roomId,
            user_name: userName,
            zoom: mediaZoomPercent,
            fx: Number(frac.fx.toFixed(4)),
            fy: Number(frac.fy.toFixed(4))
        });
    }

    function applyRemoteMediaView(data) {
        if (!data || isOwner) return;
        const vp = getMediaViewport();
        if (!vp || vp.style.display === 'none' || !getActiveMediaEl()) return;
        if (typeof data.zoom === 'number' && data.zoom !== mediaZoomPercent) {
            mediaZoomPercent = Math.max(0, Math.min(400, Math.round(data.zoom)));
            lastZoomKey = '';
            applyMediaZoom({ force: true, keepScroll: false });
        }
        const frac = { fx: Number(data.fx) || 0, fy: Number(data.fy) || 0 };
        requestAnimationFrame(() => restoreMediaScrollFraction(frac));
    }

    function attachMediaViewportEvents() {
        const vp = getMediaViewport();
        if (!vp) return;
        const syncBtn = document.getElementById('mediaViewSyncBtn');
        if (syncBtn && isOwner) syncBtn.classList.toggle('active', mediaViewSync);
        if (!vp.dataset.viewBound) {
            vp.dataset.viewBound = '1';
            vp.addEventListener('scroll', () => {
                if (!isOwner || !mediaViewSync) return;
                if (mediaScrollRaf) return;
                mediaScrollRaf = requestAnimationFrame(() => { mediaScrollRaf = null; emitMediaView(); });
            }, { passive: true });
        }
        if (!vp.dataset.zoomBound && typeof ResizeObserver !== 'undefined') {
            vp.dataset.zoomBound = '1';
            const ro = new ResizeObserver(() => {
                if (!getActiveMediaEl() || mediaZoomRaf) return;
                mediaZoomRaf = requestAnimationFrame(() => { mediaZoomRaf = null; applyMediaZoom(); });
            });
            ro.observe(vp);
        }
    }'''


PEN_D = r'''

    // ===== Zouti edisyon (stylos, flambo, kadran, flèch, gom) — mèt sal la =====
    // NOTE: `isOwner` is declared once near the top of this script (server
    // context block). Do NOT redeclare it here — a duplicate top-level `const`
    // is a fatal SyntaxError that kills the whole script before the socket
    // ever connects.
    let penActive = false;
    let currentAnnTool = 'pen'; // pen | highlight | rect | arrow | eraser
    let currentAnnColor = '#FF2D55';
    let currentAnnSize = 3;
    // Stored strokes: {tool, color, n, path|rect|arrow, sid, _ts, _by}
    // Coordinates are normalized (0..1) inside the media box and `n` is the
    // line width as a fraction of that box width => zoom/scroll proof.
    const annStrokes = [];
    let annDrawing = false;
    let annPath = [];
    let annStartPt = null;
    let annWindowBound = false;

    function annCursorFor(tool) {
        if (tool === 'rect' || tool === 'arrow' || tool === 'eraser') return 'crosshair';
        return 'cell';
    }

    function newStrokeId() {
        return 'st' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
    }

    function normLineWidth(canvas, px) {
        const w = (canvas && (canvas._cssW || canvas.clientWidth)) || 800;
        return Math.max(1, Math.min(400, Number(px) || 3)) / w;
    }

    function syncAnnButtons() {
        const map = {pen:'annPenBtn', highlight:'annHighlightBtn', rect:'annRectBtn', arrow:'annArrowBtn', eraser:'annEraserBtn'};
        document.querySelectorAll('.konf-ann-btn').forEach(b => b.classList.remove('active'));
        const active = document.getElementById(map[currentAnnTool] || '');
        if (active) active.classList.add('active');
        const penBtn = document.getElementById('mediaPenBtn');
        if (penBtn) penBtn.classList.toggle('active', penActive);
    }

    function togglePenTool() {
        penActive = !penActive;
        const toolbar = document.getElementById('mediaAnnotationToolbar');
        const media = getActiveMediaEl();
        if (penActive && !media) {
            showToast('<i class="fas fa-info-circle"></i> Zouti edisyon an mache sou medya ki afiche a. Chwazi yon imaj oswa yon videyo premye.', 'info', 4500);
            penActive = false;
            syncAnnButtons();
            return;
        }
        if (toolbar) toolbar.style.display = (penActive && media) ? 'flex' : 'none';
        syncMediaPenLayer();
        syncAnnButtons();
        showToast(penActive
            ? '<i class="fas fa-pen"></i> Zouti edisyon aktif! Trase, souliye, kadre, flèch oswa gome sou medya a.'
            : '<i class="fas fa-pen-slash"></i> Zouti edisyon dezaktive.', 'info', 2500);
    }

    function setAnnTool(tool) {
        currentAnnTool = tool;
        const canvas = document.getElementById('mediaAnnotationCanvas');
        if (canvas) canvas.style.cursor = annCursorFor(tool);
        syncAnnButtons();
        const names = {pen:'Stylos', highlight:'Flambo', rect:'Kadran', arrow:'Flèch', eraser:'Gom'};
        showToast('<i class="fas fa-mouse-pointer"></i> Zouti: <b>' + (names[tool] || tool) + '</b>', 'info', 1500);
    }

    function setAnnColor(c) { currentAnnColor = c; }
    function setAnnSize(s) { currentAnnSize = s; }'''


PEN_E = r'''

    // The canvas is re-created on demand: showMediaInMain() empties the stage
    // (which used to destroy the old canvas and silently break the pen tool),
    // so every entry point goes through this helper.
    function ensureAnnotationCanvas() {
        const stage = getMediaStage();
        if (!stage) return null;
        let canvas = document.getElementById('mediaAnnotationCanvas');
        if (canvas && canvas.parentElement !== stage) {
            canvas.remove();
            canvas = null;
        }
        if (!canvas) {
            canvas = document.createElement('canvas');
            canvas.className = 'konf-media-annotation-canvas';
            canvas.id = 'mediaAnnotationCanvas';
            canvas.style.display = 'none';
            stage.appendChild(canvas);
        }
        attachCanvasEvents();
        return canvas;
    }

    function syncMediaPenLayer() {
        const canvas = ensureAnnotationCanvas();
        const media = getActiveMediaEl();
        const toolbar = document.getElementById('mediaAnnotationToolbar');
        if (toolbar) toolbar.style.display = (penActive && media) ? 'flex' : 'none';
        if (!canvas) return;
        if (!media) {
            canvas.style.display = 'none';
            canvas.style.pointerEvents = 'none';
            return;
        }
        resizeAnnotationCanvas();
        canvas.style.display = penActive ? 'block' : 'none';
        canvas.style.pointerEvents = penActive ? 'auto' : 'none';
        canvas.style.cursor = annCursorFor(currentAnnTool);
    }

    // The canvas is glued to the media box (offsetLeft/offsetTop inside the
    // stage), NOT to the viewport: when the teacher scrolls or zooms, the
    // canvas follows the document automatically, and canvasPoint() keeps
    // converting pointer positions into the same normalized space.
    function resizeAnnotationCanvas() {
        const stage = getMediaStage();
        const canvas = document.getElementById('mediaAnnotationCanvas');
        const media = getActiveMediaEl();
        if (!stage || !canvas || !media) return;
        const run = () => {
            const w = Math.max(1, Math.round(media.offsetWidth || stage.offsetWidth || 1));
            const h = Math.max(1, Math.round(media.offsetHeight || stage.offsetHeight || 1));
            const dpr = window.devicePixelRatio || 1;
            canvas.style.position = 'absolute';
            canvas.style.left = (media.offsetLeft || 0) + 'px';
            canvas.style.top = (media.offsetTop || 0) + 'px';
            canvas.style.width = w + 'px';
            canvas.style.height = h + 'px';
            canvas.width = Math.max(1, Math.round(w * dpr));
            canvas.height = Math.max(1, Math.round(h * dpr));
            canvas._cssW = w;
            canvas._cssH = h;
            canvas._dpr = dpr;
            const ctx = canvas.getContext('2d');
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            redrawAnnotations();
        };
        if (media.tagName === 'IMG' && !(media.complete && media.naturalWidth)) {
            media.addEventListener('load', run, { once: true });
            return;
        }
        run();
    }

    function canvasPoint(evt) {
        const canvas = document.getElementById('mediaAnnotationCanvas');
        if (!canvas) return { x: 0, y: 0, px: 0, py: 0, w: 1, h: 1 };
        const rect = canvas.getBoundingClientRect();
        const p = evt.touches && evt.touches[0] ? evt.touches[0] : evt;
        const w = rect.width || 1;
        const h = rect.height || 1;
        const px = p.clientX - rect.left;
        const py = p.clientY - rect.top;
        return {
            px: px,
            py: py,
            w: w,
            h: h,
            x: Math.min(1, Math.max(0, px / w)),
            y: Math.min(1, Math.max(0, py / h))
        };
    }'''


PEN_F = r'''

    function attachCanvasEvents() {
        const canvas = document.getElementById('mediaAnnotationCanvas');
        if (!canvas || canvas.dataset.bound) return;
        canvas.dataset.bound = '1';
        const start = (e) => {
            if (!penActive) return;
            e.preventDefault();
            const pt = canvasPoint(e);
            annDrawing = true;
            annStartPt = pt;
            if (currentAnnTool === 'pen' || currentAnnTool === 'highlight') {
                annPath = [pt];
                redrawAnnotations();
                drawLiveStroke();
            } else if (currentAnnTool === 'eraser') {
                eraseStrokeAt(pt);
            }
        };
        const move = (e) => {
            if (!penActive) return;
            const pt = canvasPoint(e);
            if (currentAnnTool === 'eraser' && !annDrawing) {
                redrawAnnotations();
                drawEraserHint(pt);
                return;
            }
            if (!annDrawing) return;
            e.preventDefault();
            if (currentAnnTool === 'pen' || currentAnnTool === 'highlight') {
                annPath.push(pt);
                redrawAnnotations();
                drawLiveStroke();
            } else if (currentAnnTool === 'eraser') {
                eraseStrokeAt(pt);
            } else {
                redrawAnnotations();
                drawLiveShape(pt);
            }
        };
        const end = (e) => {
            if (!annDrawing || !penActive) return;
            e && e.preventDefault && e.preventDefault();
            annDrawing = false;
            let stroke = null;
            const color = currentAnnTool === 'highlight'
                ? (hexToRgba(currentAnnColor, 0.35) || currentAnnColor)
                : currentAnnColor;
            if (currentAnnTool === 'pen' || currentAnnTool === 'highlight') {
                if (annPath.length > 0) {
                    const px = currentAnnTool === 'highlight' ? Math.max(6, currentAnnSize * 4) : currentAnnSize;
                    stroke = {
                        tool: currentAnnTool,
                        color: color,
                        n: normLineWidth(canvas, px),
                        path: annPath.map(p => ({ x: +p.x.toFixed(4), y: +p.y.toFixed(4) })),
                        sid: newStrokeId()
                    };
                }
                annPath = [];
            } else if (currentAnnTool === 'rect' && annStartPt) {
                const endPt = (e && (e.clientX !== undefined || (e.touches && e.touches.length))) ? canvasPoint(e) : annStartPt;
                stroke = {
                    tool: 'rect',
                    color: currentAnnColor,
                    n: normLineWidth(canvas, Math.max(2, currentAnnSize)),
                    rect: { x1: annStartPt.x, y1: annStartPt.y, x2: endPt.x, y2: endPt.y },
                    sid: newStrokeId()
                };
            } else if (currentAnnTool === 'arrow' && annStartPt) {
                const endPt = (e && (e.clientX !== undefined || (e.touches && e.touches.length))) ? canvasPoint(e) : annStartPt;
                stroke = {
                    tool: 'arrow',
                    color: currentAnnColor,
                    n: normLineWidth(canvas, Math.max(2, currentAnnSize)),
                    arrow: { x1: annStartPt.x, y1: annStartPt.y, x2: endPt.x, y2: endPt.y },
                    sid: newStrokeId()
                };
            }
            if (stroke) {
                stroke._ts = Date.now();
                stroke._by = userName;
                annStrokes.push(stroke);
                if (isOwner) {
                    socket.emit('media_annotation', {
                        room_id: roomId,
                        user_name: userName,
                        stroke: stroke
                    });
                }
            }
            redrawAnnotations();
            annStartPt = null;
        };
        canvas.addEventListener('mousedown', start);
        canvas.addEventListener('mousemove', move);
        canvas.addEventListener('mouseup', end);
        canvas.addEventListener('mouseleave', (e) => {
            if (annDrawing) end(e);
            else if (penActive) redrawAnnotations();
        });
        canvas.addEventListener('touchstart', start, { passive: false });
        canvas.addEventListener('touchmove', move, { passive: false });
        canvas.addEventListener('touchend', end, { passive: false });
        if (!annWindowBound) {
            annWindowBound = true;
            window.addEventListener('resize', () => applyMediaZoom());
            document.addEventListener('keydown', handleMediaShortcut);
        }
    }'''


PEN_G = r'''

    // ===== Gom (eraser): hit-test each stroke and drop the one under the pen =====
    function strokeSegments(s, w, h) {
        const legacy = (s.n === undefined);
        const SX = (v) => legacy ? v : v * w;
        const SY = (v) => legacy ? v : v * h;
        if ((s.tool === 'pen' || s.tool === 'highlight') && s.path) {
            const out = [];
            for (let i = 1; i < s.path.length; i++) {
                out.push({
                    x1: SX(s.path[i - 1].x), y1: SY(s.path[i - 1].y),
                    x2: SX(s.path[i].x), y2: SY(s.path[i].y)
                });
            }
            return out;
        }
        if (s.tool === 'rect' && s.rect) {
            const ax = SX(s.rect.x1), ay = SY(s.rect.y1), bx = SX(s.rect.x2), by = SY(s.rect.y2);
            return [
                { x1: ax, y1: ay, x2: bx, y2: ay },
                { x1: bx, y1: ay, x2: bx, y2: by },
                { x1: bx, y1: by, x2: ax, y2: by },
                { x1: ax, y1: by, x2: ax, y2: ay }
            ];
        }
        if (s.tool === 'arrow' && s.arrow) {
            return [{ x1: SX(s.arrow.x1), y1: SY(s.arrow.y1), x2: SX(s.arrow.x2), y2: SY(s.arrow.y2) }];
        }
        return [];
    }

    function distToSegment(p, seg) {
        const dx = seg.x2 - seg.x1;
        const dy = seg.y2 - seg.y1;
        const len2 = dx * dx + dy * dy;
        let t = 0;
        if (len2 > 0) t = Math.max(0, Math.min(1, ((p.x - seg.x1) * dx + (p.y - seg.y1) * dy) / len2));
        return Math.hypot(p.x - (seg.x1 + t * dx), p.y - (seg.y1 + t * dy));
    }

    function eraseStrokeAt(pt) {
        const canvas = document.getElementById('mediaAnnotationCanvas');
        if (!canvas) return false;
        const w = canvas._cssW || canvas.clientWidth || 1;
        const h = canvas._cssH || canvas.clientHeight || 1;
        const radius = Math.max(8, (currentAnnSize || 3) * 1.6);
        for (let i = annStrokes.length - 1; i >= 0; i--) {
            const segs = strokeSegments(annStrokes[i], w, h);
            const hit = segs.some(seg => distToSegment({ x: pt.px, y: pt.py }, seg) <= radius);
            if (hit) {
                const removed = annStrokes.splice(i, 1)[0];
                redrawAnnotations();
                drawEraserHint(pt);
                if (isOwner) {
                    socket.emit('media_annotation_remove', {
                        room_id: roomId,
                        sid: removed.sid,
                        user_name: userName
                    });
                }
                return true;
            }
        }
        redrawAnnotations();
        drawEraserHint(pt);
        return false;
    }

    function drawEraserHint(pt) {
        const canvas = document.getElementById('mediaAnnotationCanvas');
        if (!canvas || !pt || currentAnnTool !== 'eraser') return;
        const ctx = canvas.getContext('2d');
        ctx.save();
        ctx.setLineDash([4, 3]);
        ctx.strokeStyle = 'rgba(239,68,68,0.9)';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(pt.px, pt.py, Math.max(8, (currentAnnSize || 3) * 1.6), 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
    }'''


PEN_H = r'''

    function hexToRgba(hex, alpha) {
        const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex || '');
        if (!m) return null;
        const r = parseInt(m[1], 16), g = parseInt(m[2], 16), b = parseInt(m[3], 16);
        return `rgba(${r}, ${g}, ${b}, ${alpha})`;
    }

    // Draws a stored stroke. Normalized strokes (n defined) are scaled to the
    // current canvas box; legacy pixel strokes still render (n undefined).
    function drawStroke(ctx, s, w, h) {
        if (!s) return;
        const legacy = (s.n === undefined);
        const SX = (v) => legacy ? v : v * w;
        const SY = (v) => legacy ? v : v * h;
        ctx.save();
        ctx.lineJoin = 'round';
        ctx.lineCap = 'round';
        ctx.strokeStyle = s.color || '#000';
        ctx.fillStyle = s.color || '#000';
        ctx.lineWidth = Math.max(1, legacy ? (s.size || 3) : (s.n || 0.004) * w);
        if (s.tool === 'pen' || s.tool === 'highlight') {
            const p = s.path || [];
            if (p.length === 0) { ctx.restore(); return; }
            ctx.beginPath();
            ctx.moveTo(SX(p[0].x), SY(p[0].y));
            for (let i = 1; i < p.length; i++) ctx.lineTo(SX(p[i].x), SY(p[i].y));
            ctx.stroke();
        } else if (s.tool === 'rect' && s.rect) {
            const x1 = SX(s.rect.x1), y1 = SY(s.rect.y1), x2 = SX(s.rect.x2), y2 = SY(s.rect.y2);
            ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
        } else if (s.tool === 'arrow' && s.arrow) {
            const x1 = SX(s.arrow.x1), y1 = SY(s.arrow.y1), x2 = SX(s.arrow.x2), y2 = SY(s.arrow.y2);
            ctx.beginPath();
            ctx.moveTo(x1, y1);
            ctx.lineTo(x2, y2);
            ctx.stroke();
            const angle = Math.atan2(y2 - y1, x2 - x1);
            const head = Math.max(8, ctx.lineWidth * 4);
            ctx.beginPath();
            ctx.moveTo(x2, y2);
            ctx.lineTo(x2 - head * Math.cos(angle - Math.PI / 6), y2 - head * Math.sin(angle - Math.PI / 6));
            ctx.lineTo(x2 - head * Math.cos(angle + Math.PI / 6), y2 - head * Math.sin(angle + Math.PI / 6));
            ctx.closePath();
            ctx.fill();
        }
        ctx.restore();
    }

    function drawLiveStroke() {
        const canvas = document.getElementById('mediaAnnotationCanvas');
        if (!canvas || annPath.length === 0) return;
        const w = canvas._cssW || canvas.clientWidth || 1;
        const h = canvas._cssH || canvas.clientHeight || 1;
        const color = currentAnnTool === 'highlight'
            ? (hexToRgba(currentAnnColor, 0.35) || currentAnnColor)
            : currentAnnColor;
        const px = currentAnnTool === 'highlight' ? Math.max(6, currentAnnSize * 4) : currentAnnSize;
        drawStroke(canvas.getContext('2d'), { tool: currentAnnTool, color: color, n: normLineWidth(canvas, px), path: annPath }, w, h);
    }

    function drawLiveShape(curPt) {
        const canvas = document.getElementById('mediaAnnotationCanvas');
        if (!canvas || !annStartPt || !curPt) return;
        const ctx = canvas.getContext('2d');
        const w = canvas._cssW || canvas.clientWidth || 1;
        const h = canvas._cssH || canvas.clientHeight || 1;
        const x1 = annStartPt.x * w, y1 = annStartPt.y * h;
        const x2 = curPt.x * w, y2 = curPt.y * h;
        ctx.save();
        ctx.setLineDash([6, 4]);
        ctx.lineJoin = 'round';
        ctx.lineCap = 'round';
        ctx.strokeStyle = currentAnnColor;
        ctx.lineWidth = Math.max(2, currentAnnSize);
        if (currentAnnTool === 'rect') {
            ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
        } else if (currentAnnTool === 'arrow') {
            ctx.beginPath();
            ctx.moveTo(x1, y1);
            ctx.lineTo(x2, y2);
            ctx.stroke();
        }
        ctx.restore();
    }

    function redrawAnnotations() {
        const canvas = document.getElementById('mediaAnnotationCanvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const dpr = canvas._dpr || window.devicePixelRatio || 1;
        const w = canvas._cssW || canvas.clientWidth || Math.round(canvas.width / dpr);
        const h = canvas._cssH || canvas.clientHeight || Math.round(canvas.height / dpr);
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, w, h);
        for (const s of annStrokes) drawStroke(ctx, s, w, h);
    }'''


PEN_I = r'''

    function undoAnnotation() {
        if (!isOwner) return;
        if (annStrokes.length === 0) {
            showToast('<i class="fas fa-info-circle"></i> Pa gen tras pou anile.', 'info', 2000);
            return;
        }
        const removed = annStrokes.pop();
        redrawAnnotations();
        socket.emit('media_annotation_undo', {
            room_id: roomId,
            removed_ts: removed && removed._ts,
            sid: removed && removed.sid
        });
    }

    function clearAnnotations() {
        if (!isOwner) return;
        annStrokes.length = 0;
        redrawAnnotations();
        socket.emit('media_annotation_clear', { room_id: roomId });
        showToast('<i class="fas fa-trash-alt"></i> Tout anotasyon yo efase.', 'info', 2200);
    }

    // Export the annotated page as a PNG (media + strokes composited)
    function downloadAnnotatedMedia() {
        const media = getActiveMediaEl();
        const canvas = document.getElementById('mediaAnnotationCanvas');
        if (!media || !canvas) {
            showToast('<i class="fas fa-info-circle"></i> Pa gen medya sou ekran an.', 'info', 2600);
            return;
        }
        if (media.tagName !== 'IMG' && media.tagName !== 'VIDEO') {
            showToast('<i class="fas fa-info-circle"></i> Telechajman ak anotasyon disponib pou imaj ak videyo. Pou lòt kalite, pran yon kopi ekran (screenshot).', 'info', 4400);
            return;
        }
        const w = canvas._cssW || media.offsetWidth || 1;
        const h = canvas._cssH || media.offsetHeight || 1;
        try {
            const out = document.createElement('canvas');
            out.width = Math.max(1, Math.round(w));
            out.height = Math.max(1, Math.round(h));
            const octx = out.getContext('2d');
            octx.fillStyle = '#ffffff';
            octx.fillRect(0, 0, out.width, out.height);
            octx.drawImage(media, 0, 0, out.width, out.height);
            octx.drawImage(canvas, 0, 0, out.width, out.height);
            const base = (currentMediaName || 'medya')
                .replace(/[^\w.\-]+/g, '_')
                .replace(/\.[a-z0-9]+$/i, '');
            const link = document.createElement('a');
            link.download = base + '_anote_' + Date.now() + '.png';
            link.href = out.toDataURL('image/png');
            document.body.appendChild(link);
            link.click();
            link.remove();
            showToast('<i class="fas fa-download"></i> Imaj anote a telechaje.', 'success', 2600);
        } catch (err) {
            showToast('<i class="fas fa-exclamation-triangle"></i> Pa t kapab ekspòte imaj la (medya pwoteje). Eseye yon kopi ekran.', 'info', 4400);
        }
    }

    // Keyboard shortcuts for live teaching: P/H/R/A/E tools, Ctrl+Z undo,
    // +/- zoom, 0 reset, PageUp/PageDown to flip through a long document.
    function handleMediaShortcut(e) {
        const display = document.getElementById('mediaDisplay');
        if (!display || display.style.display === 'none') return;
        const target = e.target || {};
        const tag = (target.tagName || '').toUpperCase();
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable) return;
        if (e.ctrlKey || e.metaKey) {
            if ((e.key === 'z' || e.key === 'Z') && isOwner && penActive) {
                e.preventDefault();
                undoAnnotation();
            }
            return;
        }
        const tools = { p: 'pen', h: 'highlight', r: 'rect', a: 'arrow', e: 'eraser' };
        const key = (e.key || '').toLowerCase();
        if (tools[key]) {
            if (!isOwner) return;
            e.preventDefault();
            if (!penActive) togglePenTool();
            setAnnTool(tools[key]);
            return;
        }
        if (e.key === '+' || e.key === '=') { e.preventDefault(); zoomMedia(1); }
        else if (e.key === '-' || e.key === '_') { e.preventDefault(); zoomMedia(-1); }
        else if (e.key === '0') { e.preventDefault(); resetMediaZoom(); }
        else if (e.key === 'PageDown') { e.preventDefault(); scrollMediaPage(1); }
        else if (e.key === 'PageUp') { e.preventDefault(); scrollMediaPage(-1); }
    }'''


PEN_J = r'''

    // ===== Réception des actions du mèt (live pour tout moun nan sal la) =====
    socket.on('media_annotation', (data) => {
        if (!data || !data.stroke) return;
        const stroke = data.stroke;
        // Ignore the echo of our own stroke (sid) — fallback on the old timestamp guard
        if (stroke.sid && annStrokes.some(s => s.sid === stroke.sid)) return;
        if (!stroke.sid && stroke._ts && Math.abs(stroke._ts - Date.now()) < 3000) return;
        annStrokes.push(stroke);
        redrawAnnotations();
    });
    socket.on('media_annotation_remove', (data) => {
        if (!data || !data.sid) return;
        const idx = annStrokes.findIndex(s => s.sid === data.sid);
        if (idx >= 0) {
            annStrokes.splice(idx, 1);
            redrawAnnotations();
        }
    });
    socket.on('media_annotation_undo', (data) => {
        const sid = data && data.sid;
        let idx = -1;
        if (sid) idx = annStrokes.findIndex(s => s.sid === sid);
        // No sid (older client): fall back to popping the last stroke, but never
        // pop twice for the owner who already removed its own stroke locally.
        if (idx < 0 && !sid && annStrokes.length > 0) idx = annStrokes.length - 1;
        if (idx >= 0) {
            annStrokes.splice(idx, 1);
            redrawAnnotations();
        }
    });
    socket.on('media_annotation_clear', () => {
        annStrokes.length = 0;
        redrawAnnotations();
    });

    // ===== Swiv an dirèk: elèv yo swiv zoum + defilman mèt la =====
    socket.on('media_view', (data) => {
        applyRemoteMediaView(data);
    });'''

PEN_NEW = (PEN_A + PEN_B + PEN_C + PEN_D + PEN_E + PEN_F + PEN_G + PEN_H + PEN_I + PEN_J)



# ---------------------------------------------------------------------------
# 8) konferans.css — the requested scroll bar + the zoom/stage styles
# ---------------------------------------------------------------------------
CSS1_OLD = r'''.konf-media-display-content {
    padding: 16px;
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 200px;
    transition: all 0.3s ease;
}'''

CSS1_NEW = r'''/* ===== Media Display Viewport: scroll bar (defilman) + zoom ===== */
.konf-media-display-content {
    position: relative;
    padding: 16px;
    display: flex;
    justify-content: center;
    align-items: flex-start;
    min-height: 200px;
    max-height: 62vh;
    overflow: auto;                 /* <- the visible scroll bar the teacher uses */
    overscroll-behavior: contain;
    -webkit-overflow-scrolling: touch;
    background-color: #0b1220;
    background-image:
        linear-gradient(45deg, rgba(255,255,255,0.03) 25%, transparent 25%, transparent 75%, rgba(255,255,255,0.03) 75%),
        linear-gradient(45deg, rgba(255,255,255,0.03) 25%, transparent 25%, transparent 75%, rgba(255,255,255,0.03) 75%);
    background-size: 24px 24px;
    background-position: 0 0, 12px 12px;
    scrollbar-width: thin;
    scrollbar-color: rgba(232,200,116,0.6) rgba(255,255,255,0.07);
    transition: max-height 0.3s ease;
}
.konf-media-display-content::-webkit-scrollbar { width: 12px; height: 12px; }
.konf-media-display-content::-webkit-scrollbar-track {
    background: rgba(255,255,255,0.06);
    border-radius: 8px;
    margin: 4px;
}
.konf-media-display-content::-webkit-scrollbar-thumb {
    background: linear-gradient(180deg, rgba(232,200,116,0.85), rgba(201,162,75,0.6));
    border: 2px solid #0b1220;
    border-radius: 8px;
}
.konf-media-display-content::-webkit-scrollbar-thumb:hover { background: #E8C874; }
.konf-media-display-content::-webkit-scrollbar-corner { background: rgba(255,255,255,0.06); }

/* Stage = exact box of the media; the annotation canvas is glued to it, so it
   scrolls and zooms with the document instead of floating on the viewport. */
.konf-media-stage {
    position: relative;
    display: inline-block;
    flex: 0 0 auto;
    line-height: 0;
}

/* Zoom label (click = back to "Ajiste") */
.konf-media-zoom-label {
    min-width: 54px;
    padding: 4px 8px;
    border-radius: 8px;
    text-align: center;
    font-size: 0.72rem;
    font-weight: 700;
    color: rgba(255,255,255,0.8);
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.1);
    cursor: pointer;
    user-select: none;
    transition: all 0.18s ease;
}
.konf-media-zoom-label:hover { color: #E8C874; border-color: rgba(232,200,116,0.45); }
.konf-media-zoom-label.active {
    color: #E8C874;
    background: rgba(232,200,116,0.14);
    border-color: rgba(232,200,116,0.5);
}

/* Live view-sync toggle (owner) */
#mediaViewSyncBtn.active {
    color: #4ade80;
    background: rgba(74,222,128,0.12);
    box-shadow: 0 0 0 2px rgba(74,222,128,0.15);
}'''

CSS2_OLD = r'''.konf-media-display-content img {
    max-width: 100%;
    max-height: 400px;
    border-radius: 12px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.3);
    transition: all 0.3s ease;
}
.konf-media-display-content video {
    max-width: 100%;
    max-height: 400px;
    border-radius: 12px;
    transition: all 0.3s ease;
}'''

CSS2_NEW = r'''.konf-media-display-content img {
    max-width: none;      /* rendered size is driven by applyMediaZoom() in JS */
    max-height: none;
    border-radius: 12px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.3);
    transition: box-shadow 0.3s ease;
}
.konf-media-display-content video {
    max-width: none;
    max-height: none;
    border-radius: 12px;
    transition: box-shadow 0.3s ease;
}'''

CSS3_OLD = r'''.konf-media-display.fullscreen .konf-media-display-content {
    flex: 1;
    padding: 24px;
    min-height: 0;
    background: #000;
}'''

CSS3_NEW = r'''.konf-media-display.fullscreen .konf-media-display-content {
    flex: 1;
    padding: 24px;
    min-height: 0;
    max-height: none;
    overflow: auto;
    background: #000;
}'''

CSS4_OLD = r'''.konf-media-display.fullscreen .konf-media-display-content img {
    max-width: 100%;
    max-height: 100%;
    width: auto;
    height: auto;
    object-fit: contain;
    box-shadow: none;
}
.konf-media-display.fullscreen .konf-media-display-content video {
    max-width: 100%;
    max-height: 100%;
    width: auto;
    height: auto;
    object-fit: contain;
}'''

CSS4_NEW = r'''.konf-media-display.fullscreen .konf-media-display-content img {
    max-width: none;
    max-height: none;
    object-fit: contain;
    box-shadow: none;
}
.konf-media-display.fullscreen .konf-media-display-content video {
    max-width: none;
    max-height: none;
    object-fit: contain;
}'''

CSS5_OLD = r'''    .konf-ann-size-label input[type=range] { width: 70px; }
}'''

CSS5_NEW = r'''    .konf-ann-size-label input[type=range] { width: 70px; }
    /* Media viewport (scroll + zoom) on small screens */
    .konf-media-display-content { max-height: 58vh; padding: 10px; }
    .konf-media-display-content::-webkit-scrollbar { width: 9px; height: 9px; }
    .konf-media-zoom-label { min-width: 46px; font-size: 0.68rem; padding: 3px 6px; }
}'''



# ---------------------------------------------------------------------------
# 9) konferans/routes.py — new relay events (owner-only, mirror the pen ones)
# ---------------------------------------------------------------------------
ROUTES_ANCHOR = r'''        emit('media_annotation_clear', room=room_id)'''

ROUTES_NEW = r'''        emit('media_annotation_clear', room=room_id)

    @socketio.on('media_annotation_remove')
    def handle_media_annotation_remove(data):
        """Owner erased one stroke with the eraser tool — drop it everywhere."""
        from flask_socketio import emit
        room_id = data.get('room_id')
        sid = data.get('sid')
        if not room_id or not sid or not _socket_owner(room_id, request.sid):
            return
        emit('media_annotation_remove', {
            'sid': sid,
            'user_name': data.get('user_name') or room_participants.get(room_id, {}).get(request.sid, 'Unknown'),
        }, room=room_id)

    @socketio.on('media_view')
    def handle_media_view(data):
        """Owner zoomed / scrolled the shared media — relay the viewport (zoom +
        scroll fraction) so participants follow the live edition."""
        from flask_socketio import emit
        room_id = data.get('room_id')
        if not room_id or not _socket_owner(room_id, request.sid):
            return
        try:
            zoom = int(data.get('zoom') or 0)
        except (TypeError, ValueError):
            zoom = 0

        def _frac(key):
            try:
                val = float(data.get(key) or 0)
            except (TypeError, ValueError):
                val = 0.0
            return round(min(1.0, max(0.0, val)), 4)

        emit('media_view', {
            'zoom': max(0, min(400, zoom)),
            'fx': _frac('fx'),
            'fy': _frac('fy'),
            'user_name': data.get('user_name') or room_participants.get(room_id, {}).get(request.sid, 'Unknown'),
        }, room=room_id, skip_sid=request.sid)'''


def main():
    print('== templates/konferans/room.html ==')
    html = read(ROOM)
    style = '\r\n' if '\r\n' in html else '\n'
    html = apply(html, ROOM_HEADER_OLD, ROOM_HEADER_NEW, 'media header: zoom + scroll + sync buttons', style)
    html = apply(html, ROOM_TOOLBAR_OLD, ROOM_TOOLBAR_NEW, 'annotation toolbar: eraser + export', style)
    html = apply(html, ROOM_CSS_OLD, ROOM_CSS_NEW, 'css cache-buster -> v=7', style)
    html = replace_region(html, SHOW_START, SHOW_END, SHOW_NEW, 'showMediaInMain()', style)
    html = replace_region(html, CLEAR_START, CLEAR_END, CLEAR_NEW, 'clearMediaDisplay()', style)
    html = apply(html, FS_EXIT_OLD, FS_EXIT_NEW, 'fullscreen exit re-measure', style)
    html = apply(html, FS_ENTER_OLD, FS_ENTER_NEW, 'fullscreen enter re-measure', style)
    html = replace_region(html, PEN_START, PEN_END, PEN_NEW, 'scroll/zoom viewport + pen block', style)
    write(ROOM, html)

    print('== static/css/konferans.css ==')
    css = read(CSS)
    cstyle = '\r\n' if '\r\n' in css else '\n'
    css = apply(css, CSS1_OLD, CSS1_NEW, 'viewport scroll bar + zoom + stage', cstyle)
    css = apply(css, CSS2_OLD, CSS2_NEW, 'img/video sizing left to JS', cstyle)
    css = apply(css, CSS3_OLD, CSS3_NEW, 'fullscreen viewport scroll', cstyle)
    css = apply(css, CSS4_OLD, CSS4_NEW, 'fullscreen img/video sizing', cstyle)
    css = apply(css, CSS5_OLD, CSS5_NEW, 'mobile viewport tweaks', cstyle)
    write(CSS, css)

    print('== konferans/routes.py ==')
    routes = read(ROUTES)
    rstyle = '\r\n' if '\r\n' in routes else '\n'
    routes = apply(routes, ROUTES_ANCHOR, ROUTES_NEW, 'media_view + media_annotation_remove relays', rstyle)
    write(ROUTES, routes)

    print('')
    print('DONE — 3 files patched (backups in %s)' % BACKUP_DIR)


if __name__ == '__main__':
    main()

