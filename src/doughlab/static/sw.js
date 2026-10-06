// Service worker minimale: shell cache per aprire l'app offline.
const CACHE = 'doughlab-v4';
const CORE = [
  '/',
  '/static/manifest.webmanifest',
  '/static/vendor/alpine-3.14.3.min.js',
  '/static/vendor/htmx-1.9.12.min.js',
  '/static/vendor/chart-4.4.4.umd.min.js',
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(CORE)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});
self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  if (req.mode === 'navigate') {
    e.respondWith(
      fetch(req).then(resp => {
        if (resp.ok && (resp.headers.get('content-type') || '').includes('text/html')) {
          caches.open(CACHE).then(c => c.put(req, resp.clone())).catch(() => {});
        }
        return resp;
      }).catch(() => caches.match(req).then(hit => hit || caches.match('/')))
    );
    return;
  }
  // Solo gli asset statici sono cache-first: diario, ricette e foto devono arrivare sempre dalla rete.
  const url = new URL(req.url);
  if (url.origin !== self.location.origin || !url.pathname.startsWith('/static/') || url.pathname === '/static/sw.js') return;
  e.respondWith(
    caches.match(req).then(hit => hit || fetch(req).then(resp => {
      if (resp.ok) {
        const copy = resp.clone();
        caches.open(CACHE).then(c => c.put(req, copy)).catch(() => {});
      }
      return resp;
    }))
  );
});
