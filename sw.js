// Service Worker léger d'Horizon Bourse Invest : interface en cache (chargement rapide) et dernières données consultables hors connexion.
const V = "hbi-v2";
const SHELL = ["./", "index.html", "manifest.webmanifest", "icon-192.png", "icon-512.png", "apple-touch-icon.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(V).then((c) => Promise.all(SHELL.map((u) => c.add(u).catch(() => null)))).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== V).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});

function garder(req, rep) {
  if (rep && rep.ok && rep.type === "basic") { const c = rep.clone(); caches.open(V).then((ca) => ca.put(req, c)).catch(() => {}); }
  return rep;
}
// Réseau d'abord (données fraîches), cache si hors connexion ou réseau trop lent.
function reseauD(req, delai, nav) {
  const net = fetch(req).then((r) => garder(req, r));
  const lent = new Promise((res) => setTimeout(() => res(null), delai));
  return Promise.race([net, lent]).then((r) => r || caches.match(req, { ignoreSearch: true }).then((c) => c || net))
    .catch(() => caches.match(req, { ignoreSearch: true }).then((c) => c || (nav ? caches.match("index.html") : Response.error())));
}
// Cache d'abord, mise à jour en arrière-plan (images, icônes).
function cacheD(req) {
  return caches.match(req, { ignoreSearch: true }).then((c) => {
    const net = fetch(req).then((r) => garder(req, r)).catch(() => c);
    return c || net;
  });
}
self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const u = new URL(req.url);
  if (u.origin !== location.origin) return;
  if (req.mode === "navigate") return e.respondWith(reseauD(req, 4000, true));
  if (/\.json$/i.test(u.pathname)) return e.respondWith(reseauD(req, 6000, false));
  if (/\.(png|jpe?g|svg|ico|webmanifest)$/i.test(u.pathname)) return e.respondWith(cacheD(req));
});
