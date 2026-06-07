// v202606070351
self.addEventListener("install", e => self.skipWaiting());
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(k => Promise.all(k.map(c => caches.delete(c)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  e.respondWith(fetch(e.request, {cache:"no-store"}));
});
