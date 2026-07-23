// ═══════════════════════════════════════════════════════
// Glory2YahPub Service Worker v2.0
// Progressive Web App - Intelligent Caching Strategy
// ═══════════════════════════════════════════════════════

const CACHE_VERSION = 'glory2yahpub-v2';
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const DYNAMIC_CACHE = `${CACHE_VERSION}-dynamic`;
const IMAGE_CACHE = `${CACHE_VERSION}-images`;
const API_CACHE = `${CACHE_VERSION}-api`;

// ───── Resources to pre-cache on install ─────
const PRECACHE_URLS = [
  '/',
  '/static/manifest.json',
  '/static/css/style.css',
  '/static/css/pwa.css',
  '/static/css/g2y-app.css',
  '/static/js/install.js',
  '/static/images/logo.png',
  '/pwa/offline'
];

// ───── INSTALL EVENT ─────
self.addEventListener('install', event => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then(cache => {
        return cache.addAll(PRECACHE_URLS);
      })
      .then(() => {
        console.log('[SW] Static assets cached successfully');
      })
      .catch(err => {
        console.warn('[SW] Some assets failed to pre-cache:', err);
      })
  );
});

// ───── ACTIVATE EVENT - Cleanup old caches ─────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames
          .filter(name => name.startsWith('glory2yahpub-') && name !== CACHE_VERSION)
          .map(name => {
            console.log('[SW] Deleting old cache:', name);
            return caches.delete(name);
          })
      );
    }).then(() => {
      console.log('[SW] Service Worker activated and old caches cleaned');
      return self.clients.claim();
    })
  );
});

// ───── FETCH EVENT - Intelligent caching strategy ─────
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);
  
  // Skip non-GET requests
  if (request.method !== 'GET') return;
  
  // ─── API requests (Network-first, cache fallback) ───
  if (url.pathname.startsWith('/pwa/api/')) {
    event.respondWith(networkFirstWithCache(request, API_CACHE));
    return;
  }
  
  // ─── Static assets (Cache-first) ───
  if (
    url.pathname.startsWith('/static/') &&
    (url.pathname.endsWith('.css') || 
     url.pathname.endsWith('.js') ||
     url.pathname.endsWith('.json'))
  ) {
    event.respondWith(cacheFirstWithRefresh(request, STATIC_CACHE));
    return;
  }
  
  // ─── Images (Cache-first, separate cache) ───
  if (
    url.pathname.startsWith('/static/images/') ||
    url.pathname.startsWith('/static/uploads/')
  ) {
    event.respondWith(cacheFirstWithRefresh(request, IMAGE_CACHE));
    return;
  }
  
  // ─── Navigation requests (Network-first) ───
  if (request.mode === 'navigate') {
    event.respondWith(networkFirstWithCache(request, DYNAMIC_CACHE));
    return;
  }
  
  // ─── All other requests (Network-first, cache fallback) ───
  event.respondWith(networkFirstWithCache(request, DYNAMIC_CACHE));
});

// ───── CACHING STRATEGIES ─────

/**
 * Cache-first strategy: Serve from cache, update cache in background
 */
async function cacheFirstWithRefresh(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cachedResponse = await cache.match(request);
  
  if (cachedResponse) {
    // Serve cached version immediately
    return cachedResponse;
  }
  
  // Not in cache, fetch from network
  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (error) {
    // Return offline page for navigation requests
    if (request.mode === 'navigate') {
      const offlineResponse = await caches.match('/pwa/offline');
      if (offlineResponse) return offlineResponse;
    }
    return new Response('Offline', { status: 503 });
  }
}

/**
 * Network-first strategy: Try network, fallback to cache
 */
async function networkFirstWithCache(request, cacheName) {
  const cache = await caches.open(cacheName);
  
  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      // Cache successful responses
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (error) {
    // Network failed, try cache
    const cachedResponse = await cache.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }
    
    // For navigation, show offline page
    if (request.mode === 'navigate') {
      const offlineResponse = await caches.match('/pwa/offline');
      if (offlineResponse) return offlineResponse;
    }
    
    return new Response('Offline', { status: 503 });
  }
}

// ───── MESSAGE HANDLING ─────
self.addEventListener('message', event => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
  
  if (event.data && event.data.type === 'CLEAR_CACHE') {
    caches.keys().then(names => {
      names.forEach(name => caches.delete(name));
    });
    event.ports[0].postMessage({ success: true });
  }
});
