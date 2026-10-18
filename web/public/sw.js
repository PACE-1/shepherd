// Shepherd service worker: keeps the static app shell (page, scripts, styles, icons under /v2/)
// so the installed app opens without a network round trip. It never touches /api or any
// other path outside /v2/: those requests fall straight through to the network, so data is
// never cached and never stale. Shell files are network-first; the cache is only the offline fallback.
// ponytail: hashed assets from old releases are pruned only when the cache name changes. Add per-release pruning if size matters.
const CACHE = "shepherd-shell-v1"
const SCOPE = new URL(self.registration.scope).pathname // "/v2/"

self.addEventListener("install", () => self.skipWaiting())

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  )
})

self.addEventListener("fetch", (event) => {
  const { request } = event
  const url = new URL(request.url)
  if (request.method !== "GET" || url.origin !== self.location.origin) return
  if (!url.pathname.startsWith(SCOPE) || url.pathname.startsWith("/api")) return
  event.respondWith(
    fetch(request)
      .then((res) => {
        // A redirect is the sign-in gate, not the shell: pass it on, keep nothing.
        if (res.ok && !res.redirected) {
          const copy = res.clone()
          event.waitUntil(caches.open(CACHE).then((c) => c.put(request, copy)))
        }
        return res
      })
      .catch(() => caches.match(request, { ignoreSearch: request.mode === "navigate" }).then((hit) => hit || Response.error())),
  )
})
