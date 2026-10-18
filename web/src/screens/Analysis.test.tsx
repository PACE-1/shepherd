import { cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { Analysis } from "@/screens/Analysis"

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })
const wellness = [
  { date: "2026-10-08", ctl: 50, atl: 60, tsb: -10 },
  { date: "2026-10-09", ctl: 52, atl: 58, tsb: -6 },
  { date: "2026-10-10", ctl: 54, atl: 50, tsb: 4 },
]
const CURVE = {
  window_days: 90, n_rides: 3, weight_kg: 70, current_ftp: 250, cp_w: 262.4,
  rider_curve: [{ duration_s: 5, watts: 900 }, { duration_s: 300, watts: 330 }, { duration_s: 1200, watts: 270 }],
  pg_2011_baseline: [{ duration_s: 5, watts_per_kg: 14, watts_at_current_weight: 980 }, { duration_s: 300, watts_per_kg: 6, watts_at_current_weight: 420 }],
}
const RIDES = [{ ride_id: "icu_1", source: "icu", name: "Morning ride", started_at: "2026-10-10T07:30:00", duration_s: 5400, distance_km: 41.23, np_w: 210, avg_power_w: 190, tss: 78.4 }]

const Z = { cycling: 0, running: 0, swimming: 0, other: 0 }
const EMPTY_BUCKET = { key: "2026-W42", label: "Week", start: "2026-10-12", end: "2026-10-18", hours: Z, load: Z, total_hours: 0, total_load: 0, hours_share: Z, load_share: Z, gap_pp: null }

function mock(over: Record<string, () => Response> = {}) {
  const urls: string[] = []
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    urls.push(url)
    const key = Object.keys(over).find((k) => url.startsWith(k))
    if (key) return over[key]()
    if (url.startsWith("/api/wellness")) return json(wellness)
    if (url.startsWith("/api/profile/power-curve")) return json(CURVE)
    if (url.startsWith("/api/profile/tau-fits") || url.startsWith("/api/profile/fatigue-resistance")) return json({ fit_status: "insufficient_data" })
    if (url.startsWith("/api/rides")) return json(RIDES)
    if (url.startsWith("/api/analytics/weight-trend")) return json({ method: "", tau_days: 7, points: [], wkg: [] })
    if (url.startsWith("/api/analytics/power-model")) return json({ window_days: 90, n_rides: 0, method: "", caveat: "", fit: { status: "insufficient", reason: "none", points: [] }, history: [] })
    if (url.startsWith("/api/balance")) return json({ as_of: "2026-10-18", weeks: [EMPTY_BUCKET], months: [EMPTY_BUCKET], sports_present: [], single_sport: null, has_history: false, has_targets: false, targets: null, limiter: null, limiter_note: "", method: "" })
    return json({}, 404)
  }))
  return urls
}
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe("Analysis", () => {
  it("shows the latest fitness, a chart, the power curve points and recent rides", async () => {
    mock()
    render(<Analysis />)
    expect(await screen.findByText(/fitness 54 · fatigue 50 · form 4/)).toBeTruthy()
    expect(screen.getByRole("img", { name: /Fitness, fatigue and form over 3 days/ })).toBeTruthy()
    expect(await screen.findByRole("img", { name: /Best power for each duration over 3 rides/ })).toBeTruthy()
    expect(screen.getByText("900 W")).toBeTruthy()
    expect(screen.getByText("262 W")).toBeTruthy()
    expect(await screen.findByText(/Morning ride/)).toBeTruthy()
    expect(screen.getByText(/41.2 km · 210 W NP · 78 TSS/)).toBeTruthy()
  })

  it("reloads the fitness data for the chosen range", async () => {
    const urls = mock()
    render(<Analysis />)
    await screen.findByText(/fitness 54/)
    await userEvent.selectOptions(screen.getAllByLabelText("Range")[0], "365")
    await waitFor(() => expect(urls.some((u) => u === "/api/wellness?days=365")).toBe(true))
  })

  it("says so when there is no data, and keeps the other cards working when one fails", async () => {
    mock({
      "/api/wellness": () => json([]),
      "/api/profile/power-curve": () => json({ error: "boom" }, 500),
      "/api/rides": () => json([]),
    })
    render(<Analysis />)
    expect(await screen.findByText("No fitness data in this range yet.")).toBeTruthy()
    expect((await screen.findByRole("alert")).textContent).toContain("boom")
    expect(await screen.findByText(/No rides yet/)).toBeTruthy()
  })

  it("points to the backfill when rides exist but no curve is built", async () => {
    mock({ "/api/profile/power-curve": () => json({ ...CURVE, rider_curve: [], needs_backfill: true }) })
    render(<Analysis />)
    expect(await screen.findByText(/have not been read for power yet/)).toBeTruthy()
  })
})
