import { cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { diff, formFrom } from "@/lib/settings"
import { Settings } from "@/screens/Settings"

const SETTINGS = {
  weight: 70, ftp: 250, eftp: 258.4, lthr: 170, max_hr: 190, target_mode: "power", lthr_is_set: true, w_per_kg: 3.57, ftp_source: "tested_ramp", ftp_source_date: "2026-09-01T10:00:00",
  power_zones: [{ zone: "Z1", name: "Z1 Active Recovery", low: 0, high: 137 }, { zone: "Z7", name: "Z7 Neuromuscular", low: 377, high: 99999 }],
  hr_zones: [{ zone: "Z1", name: "Z1 Recovery", low: 0, high: 136 }],
}
const LIMITS = { ftp: [50, 600], weight: [30, 200], lthr: [100, 220], max_hr: [140, 220] }
const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })

function mock(over: Record<string, (body: unknown) => Response> = {}) {
  const calls: { url: string; method?: string; body: unknown }[] = []
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const body = init?.body ? JSON.parse(init.body as string) : undefined
    calls.push({ url, method: init?.method, body })
    const key = Object.keys(over).find((k) => url === k || (k !== "/api/settings" && url.startsWith(k)))
    if (key) return over[key](body)
    if (url === "/api/settings" && !init?.method) return json(SETTINGS)
    if (url === "/api/setup/limits") return json(LIMITS)
    if (url === "/api/icu/connection") return json({ connected: true, name: "Isaac", write_ok: true })
    if (url === "/api/sync/status") return json({ last_sync: { timestamp: "2026-10-16T08:00:00" }, wellness_records: 90, activity_records: 40, auth_disabled: false })
    if (url === "/api/llm") return json({ configured: false, provider: "", base_url: "", model: "", has_key: false })
    if (url === "/api/garmin") return json({ available: true, connected: false, needs_login: false, mfa_pending: false, name: "", relay_to_icu: false, last_sync_at: null, last_error: null, health_days: 0, activities_imported: 0 })
    if (url === "/api/version") return json({ app: "shepherd", version: "1.0.0", data_dir: "/data" })
    if (url === "/api/icu/push") return json({ connected: true, write_ok: true, sync_enabled: false, horizon_days: 14 })
    if (url === "/api/settings/workout-folders") return json({ builtin: { count: 4300 }, extra: null })
    if (url === "/api/profile/ftp-history") return json({ ftp_current: 250, ftp_source: "manual", history: [] })
    return json({}, 404)
  }))
  return calls
}
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe("diff", () => {
  const s = SETTINGS as never
  it("sends only what changed", () => {
    const f = { ...formFrom(s), ftp: "260", targetMode: "hr" as const }
    expect(diff(s, f, { ftp: [50, 600], weight: [30, 200], lthr: [100, 220], max_hr: [140, 220] }).changes).toEqual({ ftp: 260, target_mode: "hr" })
  })
  it("flags blanks, out-of-range values and a max HR at or below LTHR", () => {
    const lim = { ftp: [50, 600], weight: [30, 200], lthr: [100, 220], max_hr: [140, 220] } as never
    expect(diff(s, { ...formFrom(s), ftp: "" }, lim).problems).toEqual(["FTP must be a number."])
    expect(diff(s, { ...formFrom(s), ftp: "900" }, lim).problems).toEqual(["FTP must be between 50 and 600."])
    expect(diff(s, { ...formFrom(s), maxHr: "170" }, lim).problems).toEqual(["Max HR must be above LTHR."])
  })
})

describe("Settings", () => {
  it("shows the rider values, zones, sync state and version", async () => {
    mock()
    render(<Settings />)
    expect(await screen.findByDisplayValue("250")).toBeTruthy()
    expect(screen.getByText(/FTP source: tested_ramp \(2026-09-01\)/)).toBeTruthy()
    expect(screen.getByText(/intervals.icu estimates 258 W/)).toBeTruthy()
    expect(screen.getByText("377+ W")).toBeTruthy()
    expect(await screen.findByText(/Connected as Isaac/)).toBeTruthy()
    expect(screen.getByText(/40 rides and 90 wellness days stored. Last sync: 2026-10-16T08:00:00/)).toBeTruthy()
    expect(await screen.findByText("1.0.0")).toBeTruthy()
  })

  it("saves only the changed field, then shows it as saved", async () => {
    const calls = mock({ "/api/settings": (b) => (b ? json({ ok: true, updated: {}, settings: { ...SETTINGS, ftp: 260 } }) : json(SETTINGS)) })
    render(<Settings />)
    const ftp = await screen.findByDisplayValue("250")
    const save = screen.getByRole("button", { name: "Save changes" }) as HTMLButtonElement
    expect(save.disabled).toBe(true)
    await userEvent.clear(ftp)
    await userEvent.type(ftp, "260")
    await userEvent.click(save)
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.url === "/api/settings")).toBe(true))
    expect(calls.find((c) => c.method === "POST")!.body).toEqual({ ftp: 260 })
    expect(await screen.findByDisplayValue("260")).toBeTruthy()
  })

  it("blocks a bad value without calling the server", async () => {
    const calls = mock()
    render(<Settings />)
    const ftp = await screen.findByDisplayValue("250")
    await userEvent.clear(ftp)
    await userEvent.type(ftp, "5000")
    expect(await screen.findByText("FTP must be between 50 and 600.")).toBeTruthy()
    expect((screen.getByRole("button", { name: "Save changes" }) as HTMLButtonElement).disabled).toBe(true)
    expect(calls.some((c) => c.method === "POST")).toBe(false)
  })

  it("shows the server's refusal", async () => {
    mock({ "/api/settings": (b) => (b ? json({ detail: "hr mode needs your LTHR" }, 400) : json(SETTINGS)) })
    render(<Settings />)
    await userEvent.selectOptions(await screen.findByLabelText("Targets"), "hr")
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }))
    expect((await screen.findByRole("alert")).textContent).toContain("hr mode needs your LTHR")
  })

  it("syncs on demand and reports a failure", async () => {
    const calls = mock({ "/api/sync": () => json({ detail: "ICU unreachable" }, 502) })
    render(<Settings />)
    await userEvent.click(await screen.findByRole("button", { name: "Sync now" }))
    expect((await screen.findByText(/Couldn’t do that: ICU unreachable/))).toBeTruthy()
    expect(calls.filter((c) => c.url === "/api/sync/status").length).toBeGreaterThan(1)
  })

  it("disables sync when not connected and explains where to connect", async () => {
    mock({ "/api/icu/connection": () => json({ connected: false }) })
    render(<Settings />)
    expect(await screen.findByText(/Not connected/)).toBeTruthy()
    expect((screen.getByRole("button", { name: "Sync now" }) as HTMLButtonElement).disabled).toBe(true)
  })

  it("reports whether an update is available", async () => {
    mock({ "/api/update/check": () => json({ current: "1.0.0", latest: "1.1.0", update_available: true, release_url: "https://example.test/r" }) })
    render(<Settings />)
    await userEvent.click(await screen.findByRole("button", { name: "Check for updates" }))
    expect((await screen.findByRole("status")).textContent).toContain("Version 1.1.0 is available")
  })
})
