import { cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { binnedPoints, compareUrl, effortFromMinutes, fmtClock, fmtDelta } from "@/lib/analytics"
import { PowerModel } from "@/screens/PowerModel"
import { RideCompare } from "@/screens/RideCompare"
import { WeightTrend } from "@/screens/WeightTrend"

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

function mock(routes: Record<string, unknown>) {
  const urls: string[] = []
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    urls.push(url)
    const key = Object.keys(routes).find((k) => url.startsWith(k))
    return key ? json(routes[key]) : json({ error: "nope" }, 404)
  }))
  return urls
}

const TREND = {
  method: "Exponentially weighted moving average, time constant 7 days.", tau_days: 7,
  points: [{ date: "2026-09-01", weight_kg: 72, source: "manual", trend_kg: 72 }, { date: "2026-10-01", weight_kg: 70, source: "intervals.icu", trend_kg: 70.03 }],
  latest_trend_kg: 70.03, change_28d_kg: -1.97,
  wkg: [{ date: "2026-09-01", ftp_w: 280, weight_kg: 72, w_per_kg: 3.89 }, { date: "2026-10-01", ftp_w: 280, weight_kg: 70.03, w_per_kg: 4.0 }],
  latest_w_per_kg: 4.0,
}

const FIT = { status: "ok", reason: "", n_points: 4, cp_w: 249.1, wprime_j: 20377, cp_ci95_w: [244.6, 253.7], wprime_ci95_j: [17234, 23521], cp_se_w: 1.1, wprime_se_j: 731, r2: 1.0, see_j: 832,
  points: [{ duration_s: 180, watts: 365, work_j: 65700 }, { duration_s: 1200, watts: 266, work_j: 319200 }] }
const MODEL = { window_days: 90, n_rides: 12, method: "Two-parameter critical power model (Monod & Scherrer 1965).", caveat: "Treat as estimates.", fit: FIT, pmax_w: 950, weight_kg: 70, cp_w_per_kg: 3.56,
  history: [{ end_date: "2026-08-31", status: "ok", cp_w: 240 }, { end_date: "2026-09-30", status: "ok", cp_w: 249 }] }

const side = (name: string, np: number, whole = true) => ({ ride_id: name, name, started_at: "2026-10-01T08:00:00", whole, start_s: whole ? 0 : 600, end_s: 1200,
  summary: { duration_s: 3600, distance_km: 30, np_w: np, if_pct: 80, tss: 60, avg_hr: 140 }, power_w: [200, 210, 220], hr_bpm: [130, 140, null] })
const CMP = { bin_s: 5, min_best_effort_s: 10, a: side("Ride A", 200), b: side("Ride B", 220, false),
  delta: { duration_s: 0, distance_km: 0, np_w: 20, if_pct: 8, tss: 6, avg_hr: -3 }, best_efforts: [{ duration_s: 300, a_w: 250, b_w: 262, delta_w: 12 }] }

describe("analytics helpers", () => {
  it("formats signed differences, clocks and effort ranges", () => {
    expect([fmtDelta(12, " W"), fmtDelta(-1.97, " kg", 1), fmtDelta(0), fmtDelta(null)]).toEqual(["+12 W", "−2.0 kg", "±0", "—"])
    expect([fmtClock(75), fmtClock(3725)]).toEqual(["1:15", "1:02:05"])
    expect(effortFromMinutes("", "")).toEqual({})
    expect(effortFromMinutes("10", "20")).toEqual({ start: 600, end: 1200 })
    expect(effortFromMinutes("20", "10")).toBeNull()
    expect(compareUrl("icu_1", "fit_x", { start: 60 }, {})).toBe("/api/analytics/compare?a=icu_1&b=fit_x&a_start=60")
    expect(binnedPoints([100, null, 300], 30)).toEqual([{ x: 0, y: 100 }, { x: 1, y: 300 }])
  })
})

describe("WeightTrend", () => {
  it("shows the trend, the 28-day change and W/kg, with the method", async () => {
    mock({ "/api/analytics/weight-trend": TREND })
    render(<WeightTrend />)
    expect(await screen.findByText("70.0 kg")).toBeTruthy()
    expect(screen.getByText("−2.0 kg")).toBeTruthy()
    expect(screen.getByText("4.00")).toBeTruthy()
    expect(screen.getByRole("img", { name: /Weight over 2 readings/ })).toBeTruthy()
    expect(screen.getByText(/time constant 7 days/)).toBeTruthy()
  })

  it("has an empty state", async () => {
    mock({ "/api/analytics/weight-trend": { ...TREND, points: [], wkg: [], latest_trend_kg: null } })
    render(<WeightTrend />)
    expect(await screen.findByText(/No weight recorded in this range/)).toBeTruthy()
  })
})

describe("PowerModel", () => {
  it("shows CP and W′ with their 95% intervals and the fit quality", async () => {
    mock({ "/api/analytics/power-model": MODEL })
    render(<PowerModel />)
    expect(await screen.findByText("249 W (95%: 245–254)")).toBeTruthy()
    expect(screen.getByText("20.4 kJ (95%: 17.2–23.5)")).toBeTruthy()
    expect(screen.getByText(/4 efforts, R² 1.0000, error 0.8 kJ/)).toBeTruthy()
    expect(screen.getByRole("img", { name: /last 2 months/ })).toBeTruthy()
  })

  it("says why there is no model and asks again for another window", async () => {
    const urls = mock({ "/api/analytics/power-model": { ...MODEL, fit: { status: "insufficient", reason: "Needs best efforts at 3 or more durations; found 1.", n_points: 1, points: [] }, history: [] } })
    render(<PowerModel />)
    expect(await screen.findByText(/No model for this range: Needs best efforts/)).toBeTruthy()
    await userEvent.selectOptions(screen.getByRole("combobox"), "180")
    await waitFor(() => expect(urls.some((u) => u.endsWith("window_days=180"))).toBe(true))
  })
})

describe("RideCompare", () => {
  it("compares the ride it was opened from with a chosen ride", async () => {
    const urls = mock({ "/api/rides": [{ ride_id: "icu_a", name: "Ride A", started_at: "2026-10-01T08:00:00" }, { ride_id: "icu_b", name: "Ride B", started_at: "2026-10-02T08:00:00" }], "/api/analytics/compare": CMP })
    render(<RideCompare a="icu_a" />)
    const select = await screen.findByRole("combobox")
    expect(screen.getByRole("button", { name: "Compare" }).hasAttribute("disabled")).toBe(true)
    await userEvent.selectOptions(select, "icu_b")
    const inputs = screen.getAllByRole("textbox")
    await userEvent.type(inputs[2], "10")
    await userEvent.type(inputs[3], "20")
    await userEvent.click(screen.getByRole("button", { name: "Compare" }))
    expect(await screen.findByText("+20 W")).toBeTruthy()
    expect(urls.some((u) => u === "/api/analytics/compare?a=icu_a&b=icu_b&b_start=600&b_end=1200")).toBe(true)
    expect(screen.getByText("+12 W")).toBeTruthy()
    expect(screen.getByText(/B: Ride B \(10:00–20:00\)/)).toBeTruthy()
    expect(screen.getByRole("img", { name: /Power of A and B/ })).toBeTruthy()
  })

  it("blocks an effort that ends before it starts", async () => {
    mock({ "/api/rides": [] })
    render(<RideCompare a="icu_a" b="icu_b" />)
    const inputs = await screen.findAllByRole("textbox")
    await userEvent.type(inputs[0], "20")
    await userEvent.type(inputs[1], "5")
    expect(screen.getByText(/must end after it starts/)).toBeTruthy()
    expect(screen.getByRole("button", { name: "Compare" }).hasAttribute("disabled")).toBe(true)
  })
})
