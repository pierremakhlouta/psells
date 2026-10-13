// PSells' service worker. It keeps a page to show when there is no
// connection, and the icons, and nothing else: every page of PSells is live
// figures, so a page is never cached and always comes from the network. An
// address that is not a page or one of the files below is not touched at
// all, so the API and the forms reach the app exactly as without a worker.
//
// Served by nginx at /sw.js, so its scope is the whole site; registered by
// /static/register.js. Change SHELL or offline.html and raise VERSION: the
// new worker then replaces the old one and deletes its cache.

const VERSION = "1";
const CACHE = "psells-shell-v" + VERSION;
const SHELL = [
  "/static/offline.html",
  "/static/icon-192.png",
  "/static/icon-512.png",
  "/static/apple-touch-icon.png",
  "/static/manifest.webmanifest",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

// Every cache but this version's is an old one.
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((names) => Promise.all(
        names.filter((name) => name !== CACHE).map((name) => caches.delete(name))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin) {
    return;
  }

  // A page: from the network, always. Only when there is none, the offline
  // page in its place. The page itself is never stored.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() => caches.match("/static/offline.html"))
    );
    return;
  }

  // The shell's files: the stored copy at once, refreshed from the network
  // behind it, so a new icon arrives on the next visit.
  if (SHELL.includes(url.pathname)) {
    event.respondWith(
      caches.open(CACHE).then((cache) =>
        cache.match(request).then((stored) => {
          const fresh = fetch(request)
            .then((response) => {
              if (response.ok) {
                cache.put(request, response.clone());
              }
              return response;
            })
            .catch(() => stored);
          return stored || fresh;
        })
      )
    );
  }
  // Anything else is left to the browser, uncached.
});
