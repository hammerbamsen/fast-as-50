// Fast as Fifty — service worker
// v20260907-swr · app-shell stale-while-revalidate + data network-first + Web Push (U2)
//
// Historik: v20260708-push sendte ALT direkte til nettet (ingen cache) — så en
// PWA uden net viste en tom side, og hver åbning ventede på GitHub Pages før
// første pixel. Blok 7 (7/9-26):
//   * App-shell (./, index.html, manifest.json, icon.svg) serveres fra cache
//     med det samme og genhentes i baggrunden. Afviger den nye index.html fra
//     den cachede, får alle åbne vinduer besked ({type:'sw-new-version'}), så
//     dashboardet kan vise "Ny version klar · Genindlæs".
//   * Datafiler (data.json, plan.json, plan_view.json, health.json, data/*.json)
//     er network-first med cache:'no-store'. Fejler nettet, serveres den senest
//     hentede kopi med headeren X-From-Cache: 1, så appen kan vise offline-badge.
//     Gælder både relative stier og raw.githubusercontent.com/hammerbamsen/
//     fast-as-50/main/… (dashboardet henter data.json derfra for at undgå
//     Pages-deploy-forsinkelsen).
//   * Alt andet (fonts, ikoner, Worker-API, GitHub API) går direkte til nettet.
// skipWaiting + clients.claim er bevaret, push/notificationclick er uændrede.

const SW_VERSION = "20260928-swr";
const CACHE_NAME = "fast50-" + SW_VERSION;

// Scope = /fast-as-50/ på Pages, / lokalt. Alle nøgler regnes relativt hertil.
const SCOPE = new URL(self.registration.scope);
const SHELL_KEYS = ["", "manifest.json", "icon.svg"];              // "" = roden (./ og index.html)
const DATA_RE = /^(data\.json|plan\.json|plan_view\.json|health\.json|data\/[^/]+\.json)$/;
const RAW_PREFIX = "/hammerbamsen/fast-as-50/main/";

function shellKey(rel) { return new URL(rel, SCOPE).href; }

// Klassificér en request: {kind:'shell'|'data'|'other', key}
function classify(req) {
  if (req.method !== "GET") return { kind: "other" };
  let url;
  try { url = new URL(req.url); } catch (_) { return { kind: "other" }; }

  if (url.origin === SCOPE.origin && url.pathname.startsWith(SCOPE.pathname)) {
    let rel = url.pathname.slice(SCOPE.pathname.length);
    if (req.mode === "navigate" || rel === "" || rel === "index.html") return { kind: "shell", key: shellKey("") };
    if (SHELL_KEYS.includes(rel)) return { kind: "shell", key: shellKey(rel) };
    if (DATA_RE.test(rel)) return { kind: "data", key: url.origin + url.pathname };
    return { kind: "other" };
  }
  if (url.hostname === "raw.githubusercontent.com" && url.pathname.startsWith(RAW_PREFIX)) {
    const rel = url.pathname.slice(RAW_PREFIX.length);
    if (DATA_RE.test(rel)) return { kind: "data", key: url.origin + url.pathname };
  }
  return { kind: "other" };
}

async function notifyClients(msg) {
  const all = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
  for (const c of all) { try { c.postMessage(msg); } catch (_) {} }
}

// Lille, stabil fingeraftryk af en tekst (djb2) — bruges kun til at sige
// "denne index.html er en anden end den cachede", ikke til sikkerhed.
function fingerprint(txt) {
  let h = 5381;
  for (let i = 0; i < txt.length; i++) h = ((h << 5) + h + txt.charCodeAt(i)) | 0;
  return (h >>> 0).toString(16);
}

self.addEventListener("install", (e) => {
  e.waitUntil((async () => {
    try {
      const cache = await caches.open(CACHE_NAME);
      await Promise.all(SHELL_KEYS.map(async (rel) => {
        try {
          const res = await fetch(new Request(shellKey(rel), { cache: "no-store" }));
          if (res && res.ok) await cache.put(shellKey(rel), res);
        } catch (_) {}
      }));
    } catch (_) {}
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", (e) => {
  e.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)));
    await self.clients.claim();
  })());
});

// App-shell: svar fra cache straks, hent ny i baggrunden. Er index.html ny,
// får vinduerne besked. Første gang (intet i cache) ventes på nettet.
// Hvis index.html viste sig ny mens ingen (færdig) klient kunne modtage
// beskeden — typisk under selve navigationen, hvor baggrundshentningen på
// et hurtigt net er færdig før dokumentet findes — huskes versionen her og
// gives, når siden spørger (sw-get-version). Nulstilles når den nye shell
// er serveret til en navigation.
let pendingNewVersion = null;

async function staleWhileRevalidate(req, key, waitUntil) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(key);
  const isRoot = key === shellKey("");
  if (isRoot && cached && req.mode === "navigate") pendingNewVersion = null;
  // Klon FØR svaret afleveres — bagefter er body'en brugt og clone() kaster.
  const cachedCopy = (isRoot && cached) ? cached.clone() : null;
  const refresh = (async () => {
    let res;
    try { res = await fetch(new Request(key, { cache: "no-store" })); } catch (_) { return null; }
    if (!res || !res.ok) return res || null;
    let changed = false;
    if (cachedCopy) {
      try {
        const [a, b] = await Promise.all([cachedCopy.text(), res.clone().text()]);
        changed = a !== b;
        if (changed) {
          pendingNewVersion = SW_VERSION + "·" + fingerprint(b);
          await notifyClients({ type: "sw-new-version", version: pendingNewVersion });
        }
      } catch (_) {}
    }
    try { await cache.put(key, res.clone()); } catch (_) {}
    return res;
  })();
  if (cached) { waitUntil(refresh); return cached; }
  const res = await refresh;
  return res || new Response("Offline — appen er ikke hentet endnu.", { status: 503, headers: { "Content-Type": "text/plain; charset=utf-8" } });
}

// Data: nettet først (ucachet). Fejler det, den senest hentede kopi med
// X-From-Cache: 1 — så dashboardet kan vise "Offline · data kl. HH:MM".
async function networkFirst(req, key) {
  const cache = await caches.open(CACHE_NAME);
  let res;
  try {
    res = await fetch(req, { cache: "no-store" });
  } catch (_) {
    const cached = await cache.match(key);
    if (cached) return withHeader(cached, "X-From-Cache", "1");
    return new Response("", { status: 503, statusText: "Offline" });
  }
  if (res && res.ok) { try { await cache.put(key, res.clone()); } catch (_) {} }
  return res;
}

function withHeader(res, name, value) {
  const headers = new Headers(res.headers);
  headers.set(name, value);
  return new Response(res.body, { status: res.status, statusText: res.statusText, headers });
}

self.addEventListener("fetch", (e) => {
  const { kind, key } = classify(e.request);
  if (kind === "shell") { e.respondWith(staleWhileRevalidate(e.request, key, (p) => e.waitUntil(p))); return; }
  if (kind === "data")  { e.respondWith(networkFirst(e.request, key)); return; }
  if (e.request.method !== "GET") return;      // POST til Worker'en m.m.: browserens standard
  e.respondWith(fetch(e.request, { cache: "no-store" }));
});

// Dashboardet spørger om versionen til System-kortet.
self.addEventListener("message", (e) => {
  const d = e.data || {};
  if (d.type === "sw-get-version" && e.source) {
    try { e.source.postMessage({ type: "sw-version", version: SW_VERSION, cache: CACHE_NAME, newVersion: pendingNewVersion }); } catch (_) {}
  }
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
