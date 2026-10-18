/** Registers the app-shell service worker (public/sw.js, scope /v2/). Needs HTTPS or localhost; elsewhere it quietly does nothing. */
export function registerServiceWorker() {
  if (!import.meta.env.PROD || !("serviceWorker" in navigator)) return
  const base = import.meta.env.BASE_URL
  window.addEventListener("load", () => {
    navigator.serviceWorker.register(`${base}sw.js`, { scope: base }).catch(() => {})
  })
}
