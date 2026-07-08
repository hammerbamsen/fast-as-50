// Fast as Fifty — service worker
// v20260708-push · no-cache + Web Push (U2)
//
// Historik: den tidligere worker var en RESET-worker der slettede al cache og
// deregistrerede sig selv ved hver load. Den adfærd er bevaret hvor det giver
// mening (ingen caching, ryd gammel cache ved activate) — MEN selv-navigate/
// deregistrering er FJERNET, så worker'en kan overleve og modtage push.

const SW_VERSION = "20260708-push";

self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (e) => {
  e.waitUntil((async () => {
    // Ryd enhver gammel cache (vi cacher intet), men lad IKKE worker'en
    // deregistrere/navigere sig selv væk — den skal blive for at kunne
    // modtage push-beskeder.
    const keys = await caches.keys();
    await Promise.all(keys.map((k) => caches.delete(k)));
    await self.clients.claim();
  })());
});

// Alt går direkte til netværket — ingen offline-cache (bevidst valg: dashboardet
// skal altid vise friske data fra data.json/plan.json).
self.addEventListener("fetch", (e) => {
  e.respondWith(fetch(e.request, { cache: "no-store" }));
});

// -- Web Push (U2) --------------------------------------------
self.addEventListener("push", (e) => {
  let payload = {};
  try { payload = e.data ? e.data.json() : {}; } catch (_) {
    payload = { title: "Fast as Fifty", body: e.data ? e.data.text() : "" };
  }
  const title = payload.title || "Fast as Fifty";
  const options = {
    body: payload.body || "",
    icon: payload.icon || "icon.svg",
    badge: payload.badge || "icon.svg",
    tag: payload.tag || "fast50-daily",   // samme tag => erstatter, spammer ikke
    data: { url: payload.url || "./" },
    renotify: !!payload.renotify,
  };
  e.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const target = (e.notification.data && e.notification.data.url) || "./";
  e.waitUntil((async () => {
    const all = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const c of all) {
      if ("focus" in c) { try { await c.navigate(target); } catch (_) {} return c.focus(); }
    }
    if (self.clients.openWindow) return self.clients.openWindow(target);
  })());
});
