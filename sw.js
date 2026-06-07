// v202606070914
const CACHE = 'faf-v202606070914';

self.addEventListener('install', e => {
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  // data.json hentes altid frisk fra netværk
  if (url.pathname.endsWith('data.json')) {
    e.respondWith(fetch(e.request, {cache: 'no-store'}));
    return;
  }
  // Alt andet: network-first, fallback til cache
  e.respondWith(
    fetch(e.request)
      .then(resp => {
        const clone = resp.clone();
        caches.open(CACHE).then(c => c.put(e.request, clone));
        return resp;
      })
      .catch(() => caches.match(e.request))
  );
});
