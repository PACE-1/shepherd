import { cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { zoneProblem } from "@/lib/settings"
import { CalendarPush } from "@/screens/CalendarPush"
import { Diagnostics } from "@/screens/Diagnostics"
import { Folders } from "@/screens/Folders"
import { HistoryBackfill } from "@/screens/HistoryBackfill"
import { Panel } from "@/screens/panel"
import { ThemeProvider } from "@/components/theme-provider"
import { Settings } from "@/screens/Settings"
import { ZonesEditor } from "@/screens/ZonesEditor"

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })
type Handler = (body: unknown, init?: RequestInit) => Response
function mock(routes: Record<string, Handler>) {
  const calls: { url: string; method?: string; body: unknown }[] = []
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const body = typeof init?.body === "string" ? JSON.parse(init.body) : init?.body
    calls.push({ url, method: init?.method, body })
    const key = Object.keys(routes).find((k) => url === k || url.startsWith(k + "?"))
    return key ? routes[key](body, init) : json({}, 404)
  }))
  return calls
}
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe("zoneProblem", () => {
  it("accepts good rows and names the first bad one", () => {
    expect(zoneProblem([{ low: "0", high: "100" }, { low: "101", high: "200" }])).toBe("")
    expect(zoneProblem([{ low: "0", high: "100" }, { low: "", high: "200" }])).toMatch(/Zone 2: enter both/)
    expect(zoneProblem([{ low: "150", high: "100" }])).toMatch(/Zone 1: the low number must be below/)
    expect(zoneProblem([{ low: "0", high: "5000" }])).toMatch(/Zone 1/)
  })
})

describe("ZonesEditor", () => {
  const zones = [{ zone: "Z1", name: "Z1 Recovery", low: 0, high: 110 }, { zone: "Z2", name: "Z2 Endurance", low: 112, high: 150 }, { zone: "Z7", name: "Z7 Neuro", low: 302, high: 99999 }]

  it("sends every zone with the edits, and blocks a bad row", async () => {
    const calls = mock({ "/api/settings/zones": () => json({ ok: true }) })
    const saved = vi.fn()
    render(<ZonesEditor kind="power" zones={zones} unit="W" onSaved={saved} onCancel={() => {}} />)
    const high = screen.getByLabelText("Power Z1 high")
    await userEvent.clear(high)
    await userEvent.type(high, "90")
    await userEvent.click(screen.getByRole("button", { name: "Save zones" }))
    await waitFor(() => expect(saved).toHaveBeenCalled())
    expect(calls[0].body).toEqual({ kind: "power", zones: [
      { zone: "Z1", name: "Z1 Recovery", low: 0, high: 90 },
      { zone: "Z2", name: "Z2 Endurance", low: 112, high: 150 },
      { zone: "Z7", name: "Z7 Neuro", low: 302, high: 3000 },
    ] })
    await userEvent.clear(screen.getByLabelText("Power Z2 low"))
    expect(screen.getByText(/Zone 2: enter both numbers/)).toBeTruthy()
    expect((screen.getByRole("button", { name: "Save zones" }) as HTMLButtonElement).disabled).toBe(true)
  })

  it("resets to automatic zones with null", async () => {
    const calls = mock({ "/api/settings/zones": () => json({ ok: true, reset: true }) })
    const saved = vi.fn()
    render(<ZonesEditor kind="hr" zones={zones} unit="bpm" onSaved={saved} onCancel={() => {}} />)
    await userEvent.click(screen.getByRole("button", { name: "Use automatic zones" }))
    await waitFor(() => expect(saved).toHaveBeenCalled())
    expect(calls[0].body).toEqual({ kind: "hr", zones: null })
  })

  it("shows the server's refusal", async () => {
    mock({ "/api/settings/zones": () => json({ error: "zone 1: need 0 ≤ low < high ≤ 3000" }, 400) })
    render(<ZonesEditor kind="power" zones={zones} unit="W" onSaved={() => {}} onCancel={() => {}} />)
    await userEvent.click(screen.getByRole("button", { name: "Save zones" }))
    expect((await screen.findByRole("alert")).textContent).toContain("zone 1: need")
  })
})

describe("Folders", () => {
  it("adds and removes the extra folder, showing the server's reason when it is refused", async () => {
    let extra: unknown = null
    const calls = mock({
      "/api/settings/workout-folders": (b) => {
        if (b === undefined) return json({ builtin: { count: 4300 }, extra })
        const dir = (b as { extra_dir: string }).extra_dir
        if (dir === "/bad") return json({ error: "That folder has no .zwo workout files." }, 400)
        extra = dir ? { path: dir, files: 12, added: 5 } : null
        return json({ builtin: { count: 4300 }, extra })
      },
    })
    render(<Folders />)
    expect(await screen.findByText(/4300 workouts, always included/)).toBeTruthy()
    await userEvent.type(screen.getByLabelText(/Folder with your own/), "/bad")
    await userEvent.click(screen.getByRole("button", { name: "Add folder" }))
    expect((await screen.findByRole("alert")).textContent).toContain("no .zwo workout files")
    await userEvent.clear(screen.getByLabelText(/Folder with your own/))
    await userEvent.type(screen.getByLabelText(/Folder with your own/), "/home/me/zwo")
    await userEvent.click(screen.getByRole("button", { name: "Add folder" }))
    expect(await screen.findByText("/home/me/zwo")).toBeTruthy()
    expect(screen.getByText(/12 files, 5 of them add workouts/)).toBeTruthy()
    await userEvent.click(screen.getByRole("button", { name: "Remove folder" }))
    expect(await screen.findByText("No extra folder.")).toBeTruthy()
    expect(calls.at(-1)!.body).toEqual({ extra_dir: "" })
  })
})

describe("CalendarPush", () => {
  it("turns syncing on and reports a refused reconnect", async () => {
    let enabled = false
    const calls = mock({
      "/api/icu/push": (b) => (b === undefined ? json({ connected: true, write_ok: true, sync_enabled: enabled, horizon_days: 14 }) : (b as { sync?: boolean }).sync === undefined ? json({ ok: true, pushed: 3, updated: 1, deleted: 0 }) : ((enabled = (b as { sync: boolean }).sync), json({ ok: true, sync_enabled: enabled }))),
    })
    render(<CalendarPush />)
    expect(await screen.findByText(/Keeping in sync is/)).toBeTruthy()
    await userEvent.click(screen.getByRole("button", { name: "Turn on" }))
    expect((await screen.findByRole("status")).textContent).toContain("Keeping your calendar in sync.")
    expect(calls.find((c) => c.method === "POST")!.body).toEqual({ sync: true })
    await userEvent.click(screen.getByRole("button", { name: "Push the plan now" }))
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("Pushed 3, updated 1, removed 0."))
  })

  it("asks to reconnect when writing is not allowed, and says to connect first when not connected", async () => {
    mock({ "/api/icu/push": () => json({ connected: true, write_ok: false, sync_enabled: false, horizon_days: 14 }) })
    const { unmount } = render(<CalendarPush />)
    expect(await screen.findByText(/has not given this app permission/)).toBeTruthy()
    expect((screen.getByRole("button", { name: "Turn on" }) as HTMLButtonElement).disabled).toBe(true)
    unmount()
    mock({ "/api/icu/push": () => json({ connected: false }) })
    render(<CalendarPush />)
    expect(await screen.findByText("Connect intervals.icu first.")).toBeTruthy()
  })
})

describe("Diagnostics", () => {
  it("shows the log, recent errors and the failing health checks", async () => {
    const calls = mock({
      "/api/logs": () => json({ exists: true, lines: ["line one", "line two"], total: 2, path: "/x" }),
      "/api/diag/recent-errors": () => json({ count: 1, items: [{ code: "E_SYNC", ts: "2026-10-16T08:00:00", exc_msg: "timeout" }] }),
      "/api/diag/health": () => json({ ok: false, checks: { plan_readable: { ok: false, code: "E_PLAN_PARSE_MISSING" }, workout_library: { ok: true } } }),
    })
    render(<Diagnostics />)
    await userEvent.click(screen.getByRole("button", { name: "Show the log" }))
    expect((await screen.findByLabelText("Log")).textContent).toBe("line one\nline two")
    expect(calls[0].url).toBe("/api/logs?lines=100")
    await userEvent.click(screen.getByRole("button", { name: "Recent errors" }))
    expect(await screen.findByText("E_SYNC")).toBeTruthy()
    await userEvent.click(screen.getByRole("button", { name: "Check health" }))
    expect((await screen.findByRole("status")).textContent).toContain("plan readable: E_PLAN_PARSE_MISSING")
  })

  it("says so when there is no log, and shows a refusal", async () => {
    mock({ "/api/logs": () => json({ exists: false, lines: [] }), "/api/diag/health": () => json({ error: "local-only" }, 403) })
    render(<Diagnostics />)
    await userEvent.click(screen.getByRole("button", { name: "Show the log" }))
    expect(await screen.findByText("There is no log file yet.")).toBeTruthy()
    await userEvent.click(screen.getByRole("button", { name: "Check health" }))
    expect((await screen.findByRole("alert")).textContent).toContain("local-only")
  })
})

describe("HistoryBackfill", () => {
  it("starts the job, shows progress and tells the page when it is done", async () => {
    let polls = 0
    const finished = vi.fn()
    mock({
      "/api/profile/backfill-history": () => json({ status: "started", task_id: "t1" }),
      "/api/profile/backfill-history/status": () => json(++polls < 2 ? { state: "running", backfilled: 3, total: 10 } : { state: "done", backfilled: 10, failed: 0 }),
    })
    render(<HistoryBackfill onFinished={finished} pollMs={5} />)
    await userEvent.click(screen.getByRole("button", { name: "Build power history" }))
    expect((await screen.findByRole("status")).textContent).toContain("3 read of 10")
    await waitFor(() => expect(finished).toHaveBeenCalled())
    expect(screen.getByRole("status").textContent).toContain("Done: 10 rides read")
  })

  it("shows a failure to start", async () => {
    mock({ "/api/profile/backfill-history": () => json({ detail: "busy" }, 500) })
    render(<HistoryBackfill onFinished={() => {}} />)
    await userEvent.click(screen.getByRole("button", { name: "Build power history" }))
    expect((await screen.findByRole("alert")).textContent).toContain("busy")
  })
})

describe("Panel guard", () => {
  it("shows a message instead of blanking the page when a card cannot render its data", async () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {})
    render(<Panel title="Broken" load={{ state: "ok", data: null as unknown as { a: { b: number } } }} retry={() => {}}>{(d) => <p>{d.a.b}</p>}</Panel>)
    expect((await screen.findByRole("alert")).textContent).toContain("couldn’t be shown")
    spy.mockRestore()
  })
})

describe("Settings connection", () => {
  it("links to sign-in and disconnects only after a confirmation", async () => {
    let connected = true
    const calls = mock({
      "/api/settings": () => json({ weight: 70, ftp: 250, lthr: 170, max_hr: 190, target_mode: "power", power_zones: [], hr_zones: [] }),
      "/api/setup/limits": () => json({}),
      "/api/icu/connection": () => json({ connected, name: "Isaac", write_ok: true, oauth_available: true, method: connected ? "oauth" : "none" }),
      "/api/icu/disconnect": () => ((connected = false), json({ ok: true })),
      "/api/sync/status": () => json({ wellness_records: 0, activity_records: 0 }),
      "/api/version": () => json({ app: "shepherd", version: "1.0.0", data_dir: "/d" }),
      "/api/profile/ftp-history": () => json({ ftp_current: 250, history: [] }),
      "/api/sports/load": () => json({ as_of: "2026-10-18", days_of_history: 0, settled: false, combined: { ctl: 0, atl: 0, tsb: 0, week_load: 0 }, sports: {}, method: "", confidence: "" }),
      "/api/sports/thresholds": () => json({ thresholds: {} }),
      "/api/notifications/settings": () => json({ has_url: false, events: { readiness: true, missed: true, sync_failure: true }, readiness_time: "" }),
      "/api/run/zones": () => json({ pace_zones: [], hr_zones: [], method: "", confidence: "" }),
      "/api/run/activities": () => json({ runs: [], missing: [], method: "", confidence: "" }),
      "/api/icu/push": () => json({ connected: true, write_ok: true, sync_enabled: false, horizon_days: 14 }),
      "/api/settings/workout-folders": () => json({ builtin: { count: 1 }, extra: null }),
    })
    render(<ThemeProvider><Settings /></ThemeProvider>)
    expect((await screen.findByRole("link", { name: "Reconnect" })).getAttribute("href")).toBe("/oauth/icu/start?return_to=%2Fv2%2F%3Fwizard%3Dsettings")
    await userEvent.click(screen.getByRole("button", { name: "Disconnect…" }))
    expect(calls.some((c) => c.url === "/api/icu/disconnect")).toBe(false)
    await userEvent.click(screen.getByRole("button", { name: "Yes, disconnect" }))
    expect(await screen.findByRole("link", { name: "Connect intervals.icu" })).toBeTruthy()
  })
})

describe("Connect with an API key", () => {
  const base = (conn: () => Response, extra: Record<string, (b: unknown) => Response> = {}) => mock({
    "/api/settings": () => json({ weight: 70, ftp: 250, lthr: 170, max_hr: 190, target_mode: "power", power_zones: [], hr_zones: [] }),
    "/api/setup/limits": () => json({}),
    "/api/icu/connection": conn,
    "/api/sync/status": () => json({ wellness_records: 0, activity_records: 0 }),
    "/api/llm": () => json({ configured: false, provider: "", base_url: "", model: "", has_key: false }),
    "/api/version": () => json({ app: "shepherd", version: "1.0.1", data_dir: "/d" }),
    "/api/profile/ftp-history": () => json({ ftp_current: 250, history: [] }),
    "/api/sports/load": () => json({ as_of: "2026-10-18", days_of_history: 0, settled: false, combined: { ctl: 0, atl: 0, tsb: 0, week_load: 0 }, sports: {}, method: "", confidence: "" }),
    "/api/sports/thresholds": () => json({ thresholds: {} }),
    "/api/notifications/settings": () => json({ has_url: false, events: { readiness: true, missed: true, sync_failure: true }, readiness_time: "" }),
    "/api/run/zones": () => json({ pace_zones: [], hr_zones: [], method: "", confidence: "" }),
    "/api/run/activities": () => json({ runs: [], missing: [], method: "", confidence: "" }),
    "/api/icu/push": () => json({ connected: false, write_ok: false, sync_enabled: false, horizon_days: 14 }),
    "/api/settings/workout-folders": () => json({ builtin: { count: 1 }, extra: null }),
    ...extra,
  })

  it("checks the key, saves it, and hides the sign-in link when no OAuth secret is bundled", async () => {
    let connected = false
    const calls = base(() => json({ connected, method: connected ? "apikey" : "none", name: "Isaac", oauth_available: false }), {
      "/api/setup/test-icu": () => json({ ok: true, name: "Isaac", athlete_id: "i42" }),
      "/api/setup/save": () => ((connected = true), json({ ok: true })),
    })
    render(<ThemeProvider><Settings /></ThemeProvider>)
    await userEvent.click(await screen.findByRole("button", { name: "Connect with an API key" }))
    expect(screen.queryByRole("link", { name: "Connect intervals.icu" })).toBeNull()
    await userEvent.type(screen.getByLabelText("API key"), "  sekret  ")
    await userEvent.click(screen.getByRole("button", { name: "Connect" }))
    expect(await screen.findByText(/Connected as Isaac/)).toBeTruthy()
    expect(calls.find((c) => c.url === "/api/setup/test-icu")?.body).toEqual({ athlete_id: "", api_key: "sekret" })
    expect(calls.find((c) => c.url === "/api/setup/save")?.body).toEqual({ icu_athlete_id: "i42", icu_api_key: "sekret" })
  })

  it("shows intervals.icu's reason when the key is refused and saves nothing", async () => {
    const calls = base(() => json({ connected: false, method: "none", oauth_available: true }), {
      "/api/setup/test-icu": () => json({ ok: false, error: "Invalid API key." }),
    })
    render(<ThemeProvider><Settings /></ThemeProvider>)
    await userEvent.click(await screen.findByRole("button", { name: "Connect with an API key" }))
    await userEvent.type(screen.getByLabelText("API key"), "bad")
    await userEvent.click(screen.getByRole("button", { name: "Connect" }))
    expect((await screen.findByRole("alert")).textContent).toContain("Invalid API key.")
    expect(calls.some((c) => c.url === "/api/setup/save")).toBe(false)
  })
})
