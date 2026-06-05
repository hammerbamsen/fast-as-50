const CACHE = 'fast50-v1';
const STATIC = ['/', '/index.html', '/icon.svg', '/manifest.json'];
const NOCACHE = ['data.json', 'af.html'];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(STATIC))
  );
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  // data.json og af.html — altid fra nettet
  if (NOCACHE.some(p => url.pathname.endsWith(p))) {
    e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
    return;
  }
  // index.html — network first, fallback til cache
  if (url.pathname.endsWith('/') || url.pathname.endsWith('index.html')) {
    e.respondWith(
      fetch(e.request).then(res => {
        const clone = res.clone();
        caches.open(CACHE).then(c => c.put(e.request, clone));
        return res;
      }).catch(() => caches.match(e.request))
    );
    return;
  }
  // Alt andet — cache first
  e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
});
