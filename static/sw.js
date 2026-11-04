// ═══════════════════════════════════════════════════════
// Glory2YahPub Service Worker v3.0
// Progressive Web App - Offline shell + smart caching
//
// Registered from static/js/install.js as `/sw.js` (root scope), so it can
// control the whole site. Served by the `/sw.js` route in app/routes/main.py
// with `Cache-Control: no-cache` so a new version is picked up on next load.
//
// Rules of the house:
//   • GET only, same-origin only (CDN css/js is cache-first too).
//   • NEVER touch /socket.io/ or the KONFERANS room APIs — caching the polling
//     transport breaks the live video conference.
//   • NEVER cache anything the server marks `no-store` / `private, no-store`
//     (auth, admin, payments) and never cache a response that carries Set-Cookie.
//   • Navigations are network-first with an offline fallback page.
// ═══════════════════════════════════════════════════════

const CACHE_VERSION = 'glory2yahpub-v3';
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const DYNAMIC_CACHE = `${CACHE_VERSION}-dynamic`;
const IMAGE_CACHE = `${CACHE_VERSION}-images`;
const API_CACHE = `${CACHE_VERSION}-api`;
const OFFLINE_URL = '/pwa/offline';

// ───── App shell pre-cached on install ─────
const PRECACHE_URLS = [
  OFFLINE_URL,
  '/manifest.json',
  '/static/css/style.css',
  '/static/css/pwa.css',
  '/static/css/g2y-app.css',
  '/static/css/variables.css',
  '/static/css/components.css',
  '/static/js/install.js',
  '/static/images/logo.png',
  '/static/images/pwa-icons/icon-192.png',
  '/static/images/pwa-icons/icon-512.png'
];

// Paths that may be stored in the offline navigation cache (public pages only).
// Everything else (account, admin, wallet, payments…) is never stored, so a
// shared device can never replay somebody else's private HTML from the cache.
const PUBLIC_NAV_PREFIXES = [
  '/', '/mache', '/about', '/terms', '/privacy', '/auth/login', '/auth/register',
  '/pwa/offline', '/search', '/events', '/party', '/dok', '/gforms'
];

// Realtime / private surfaces the SW must stay completely out of.
const NEVER_PATHS = [
  '/socket.io',
  '/konferans',
  '/admin',
  '/bank/api',
  '/gkach/api',
  '/jere-biznis/api'
];

function isNeverCached(pathname) {
  return NEVER_PATHS.some(p => pathname === p || pathname.startsWith(p + '/') || pathname.startsWith(p + '?'));
}

function isPublicNavigation(pathname) {
  if (pathname === '/') return true;
  return PUBLIC_NAV_PREFIXES.some(p => p !== '/' && pathname.startsWith(p));
}

// ───── INSTALL ─────
self.addEventListener('install', event => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then(cache => Promise.all(PRECACHE_URLS.map(u =>
        // One failing asset must not abort the whole install (that used to leave
        // the SW installed-but-useless with an empty cache).
        cache.add(new Request(u, { cache: 'reload' })).catch(err =>
          console.warn('[SW] pre-cache skipped:', u, err && err.message))
      )))
      .then(() => console.log('[SW] pre-cached app shell'))
  );
});

// ───── ACTIVATE: drop caches from older versions ─────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(names => Promise.all(
      names
        .filter(n => n.startsWith('glory2yahpub-') && !n.startsWith(CACHE_VERSION))
        .map(n => {
          console.log('[SW] deleting old cache:', n);
          return caches.delete(n);
        })
    )).then(() => self.clients.claim())
  );
});

// ───── FETCH ─────
self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);
  const sameOrigin = url.origin === self.location.origin;

  if (request.method !== 'GET') return;
  if (isNeverCached(url.pathname)) return;
  if (!sameOrigin) {
    // Only the known CDNs are cached; anything else goes straight to the network.
    if (!/cdn\.jsdelivr\.net|cdnjs\.cloudflare\.com/.test(url.hostname)) return;
    event.respondWith(cacheFirstWithRefresh(request, STATIC_CACHE));
    return;
  }

  // App itself: never serve an offline stub for API/JSON — let it fail honestly.
  if (url.pathname.startsWith('/pwa/api/')) {
    event.respondWith(networkFirstWithCache(request, API_CACHE, false));
    return;
  }

  // Static assets: stale-while-revalidate (instant paint, refreshed in background)
  if (url.pathname.startsWith('/static/')) {
    const isImage = url.pathname.startsWith('/static/images/') || url.pathname.startsWith('/static/uploads/');
    event.respondWith(staleWhileRevalidate(request, isImage ? IMAGE_CACHE : STATIC_CACHE));
    return;
  }

  // Page navigations: network-first, offline page as last resort.
  if (request.mode === 'navigate') {
    event.respondWith(
      networkFirstWithCache(request, DYNAMIC_CACHE, isPublicNavigation(url.pathname))
    );
    return;
  }

  event.respondWith(networkFirstWithCache(request, DYNAMIC_CACHE, false));
});

// ───── STRATEGIES ─────

/**
 * Serve the cached copy immediately (if any) and refresh the cache in background.
 * Fixes the old "cache-first forever" behaviour where a returning user kept the
 * previous deploy's CSS/JS until the cache name changed.
 */
async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  const network = fetch(request).then(response => {
    if (isCacheable(response)) cache.put(request, response.clone());
    return response;
  }).catch(() => null);
  return cached || (await network) || offlineFallback(request);
}

/** Cache-first, but a miss is fetched and stored (used for pre-cached shell). */
async function cacheFirstWithRefresh(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (isCacheable(response)) cache.put(request, response.clone());
    return response;
  } catch (err) {
    return offlineFallback(request);
  }
}

/** Network-first; falls back to the stored copy, then to the offline page. */
async function networkFirstWithCache(request, cacheName, allowStore) {
  const cache = await caches.open(cacheName);
  try {
    const response = await fetch(request);
    if (allowStore && isCacheable(response)) cache.put(request, response.clone());
    return response;
  } catch (err) {
    const cached = await cache.match(request);
    if (cached) return cached;
    return offlineFallback(request);
  }
}

async function offlineFallback(request) {
  if (request.mode === 'navigate') {
    const offline = await caches.match(OFFLINE_URL);
    if (offline) return offline;
  }
  return new Response('Offline', {
    status: 503,
    headers: { 'Content-Type': 'text/plain; charset=utf-8' }
  });
}

/** Only 200, same-origin-ish, non-streamed, non-private responses may be stored. */
function isCacheable(response) {
  if (!response || response.status !== 200 || response.type === 'opaque') return false;
  if (response.headers.get('Set-Cookie')) return false;
  const cc = (response.headers.get('Cache-Control') || '').toLowerCase();
  if (cc.includes('no-store') || cc.includes('private')) return false;
  return true;
}

// ───── MESSAGES (from install.js) ─────
self.addEventListener('message', event => {
  if (!event.data) return;
  if (event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
  if (event.data.type === 'CLEAR_CACHE') {
    caches.keys().then(names => Promise.all(names.map(n => caches.delete(n))))
      .then(() => event.ports[0] && event.ports[0].postMessage({ success: true }));
  }
});
