// RESET-20260607092044
// Sletter al cache og deregistrerer sig selv
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.map(k => caches.delete(k))))
      .then(() => self.clients.claim())
      .then(() => self.clients.matchAll().then(clients => clients.forEach(c => c.navigate(c.url))))
  );
});
// Ingen caching - alt går direkte til netværk
self.addEventListener('fetch', e => {
  e.respondWith(fetch(e.request, {cache: 'no-store'}));
});
