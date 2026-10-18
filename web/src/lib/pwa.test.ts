import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it, vi } from "vitest"

type Listener = (e: unknown) => void

/** Runs public/sw.js against a fake worker scope and returns its listeners plus the fake cache and network. */
function loadWorker() {
  const listeners: Record<string, Listener> = {}
  const store = new Map<string, Response>()
  const puts: string[] = []
  const cache = { put: vi.fn(async (r: Request, res: Response) => void (puts.push(new URL(r.url).pathname), store.set(r.url, res))) }
  const caches = {
    open: async () => cache,
    keys: async () => ["old-cache", "shepherd-shell-v1"],
    delete: vi.fn(async () => true),
    match: async (r: Request) => store.get(r.url),
  }
  const network = vi.fn(async (r: Request) => new Response("net:" + new URL(r.url).pathname))
  const self = {
    registration: { scope: "http://localhost/v2/" },
    location: { origin: "http://localhost" },
    addEventListener: (type: string, fn: Listener) => void (listeners[type] = fn),
    skipWaiting: vi.fn(),
    clients: { claim: vi.fn() },
  }
  const src = readFileSync(resolve(import.meta.dirname, "../../public/sw.js"), "utf8")
  new Function("self", "caches", "fetch", src)(self, caches, network)
  const fetchEvent = async (path: string, method = "GET", origin = "http://localhost") => {
    const respondWith = vi.fn()
    const waits: Promise<unknown>[] = []
    listeners.fetch({ request: new Request(origin + path, { method }), respondWith, waitUntil: (p: Promise<unknown>) => waits.push(p) })
    const res = respondWith.mock.calls.length ? await respondWith.mock.calls[0][0] : undefined
    await Promise.all(waits)
    return { handled: respondWith.mock.calls.length > 0, res }
  }
  return { listeners, caches, network, puts, fetchEvent }
}

describe("service worker", () => {
  it("never handles or caches API or other non-shell requests", async () => {
    const w = loadWorker()
    for (const path of ["/api/profiles", "/api/plan", "/healthz", "/login", "/v2/../api/x"]) {
      const r = await w.fetchEvent(path)
      expect(r.handled, path).toBe(false)
    }
    expect((await w.fetchEvent("/v2/", "POST")).handled).toBe(false)
    expect((await w.fetchEvent("/v2/assets/x.js", "GET", "http://other.example")).handled).toBe(false)
    expect(w.puts).toEqual([])
    expect(w.network).not.toHaveBeenCalled()
  })

  it("serves the shell from the network first and keeps a copy for offline", async () => {
    const w = loadWorker()
    const online = await w.fetchEvent("/v2/assets/app.js")
    expect(await online.res.text()).toBe("net:/v2/assets/app.js")
    expect(w.puts).toEqual(["/v2/assets/app.js"])
    w.network.mockRejectedValueOnce(new TypeError("offline"))
    const offline = await w.fetchEvent("/v2/assets/app.js")
    expect((await offline.res.text()).startsWith("net:")).toBe(true)
  })

  it("does not keep a redirect (the sign-in gate) as the shell", async () => {
    const w = loadWorker()
    const redirected = new Response("login")
    Object.defineProperty(redirected, "redirected", { value: true })
    w.network.mockResolvedValueOnce(redirected)
    await w.fetchEvent("/v2/")
    expect(w.puts).toEqual([])
  })

  it("drops other cache names on activate", async () => {
    const w = loadWorker()
    const waits: Promise<unknown>[] = []
    w.listeners.activate({ waitUntil: (p: Promise<unknown>) => waits.push(p) })
    await Promise.all(waits)
    expect(w.caches.delete).toHaveBeenCalledTimes(1)
    expect(w.caches.delete).toHaveBeenCalledWith("old-cache")
  })
})
