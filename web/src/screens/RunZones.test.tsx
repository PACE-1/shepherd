import { cleanup, render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { bpmRange, paceRange } from "@/lib/run"
import { RunZones } from "@/screens/RunZones"

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })
const ZONES = (pace: number | null) => ({
  threshold_pace_s_per_km: pace,
  threshold_hr: null,
  pace_zones: pace ? [{ zone: "1", name: "Recovery", slow_s_per_km: null, fast_s_per_km: 322.5 }, { zone: "2", name: "Aerobic", slow_s_per_km: 322.5, fast_s_per_km: 285 }] : [],
  hr_zones: [],
  pace_history: [],
  method: "Joe Friel's run zones.",
  confidence: "Only as good as the threshold.",
})
const CS = (saved: boolean) => ({ cs_m_per_s: 4, cs_pace_s_per_km: 250, d_prime_m: 240, r2: null, n_trials: 2, warnings: [], method: "Linear distance-time model.", confidence: "Two trials fit the line exactly.", saved })
const RUNS = { runs: [{ id: "r1", date: "2026-10-17", name: "Easy", type: "Run", duration_s: 3600, distance_km: 12, pace_s_per_km: 300, rtss: 69.4, hrtss: null, icu_load: 70, cadence_spm: 170, cadence_doubled: true, stride_length_m: 2.35 }], missing: ["Set a run threshold heart rate to get hrTSS."], method: "rTSS.", confidence: "Average pace." }
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe("range text", () => {
  it("reads open and closed zone ends", () => {
    expect([paceRange(null, 387), paceRange(270, null), paceRange(387, 342)]).toEqual(["slower than 6:27 /km", "faster than 4:30 /km", "5:42 to 6:27 /km"])
    expect([bpmRange(null, 136), bpmRange(170, null), bpmRange(136, 142)]).toEqual(["below 136 bpm", "above 170 bpm", "136 to 142 bpm"])
  })
})

describe("RunZones", () => {
  it("computes critical speed from two trials, saves it, and shows the new zones", async () => {
    let pace: number | null = null
    const posts: unknown[] = []
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/run/zones") return json(ZONES(pace))
      if (url === "/api/run/activities") return json(RUNS)
      if (url === "/api/run/critical-speed") {
        const body = JSON.parse(init!.body as string)
        posts.push(body)
        if (body.save) pace = 250
        return json(CS(body.save))
      }
      return json({}, 404)
    }))
    render(<RunZones />)
    expect(await screen.findByText(/Set a run threshold pace/)).toBeTruthy()
    expect(within(await screen.findByRole("table", { name: "Recent runs" })).getByText("170 spm*")).toBeTruthy()
    expect(screen.getByText(/to get hrTSS/)).toBeTruthy()
    await userEvent.type(screen.getByLabelText("Trial 1 distance (m)"), "1200")
    await userEvent.type(screen.getByLabelText("Trial 1 time (m:ss)"), "4:00")
    await userEvent.type(screen.getByLabelText("Trial 2 distance (m)"), "3600")
    await userEvent.type(screen.getByLabelText("Trial 2 time (m:ss)"), "14:00")
    await userEvent.click(screen.getByRole("button", { name: "Calculate" }))
    expect(await screen.findByText(/Critical speed 4:10 \/km/)).toBeTruthy()
    expect(screen.getByText(/fit the line exactly/)).toBeTruthy()
    expect(posts[0]).toEqual({ trials: [{ distance_m: 1200, time_s: 240 }, { distance_m: 3600, time_s: 840 }], save: false })
    await userEvent.click(screen.getByRole("button", { name: "Use as threshold pace" }))
    expect((await screen.findByRole("status")).textContent).toContain("Saved 4:10 /km")
    expect(await screen.findByRole("table", { name: "Pace zones" })).toBeTruthy()
    expect(screen.getByText("slower than 5:23 /km")).toBeTruthy()
  })

  it("refuses a single trial without calling the server, and converts a pace on a slope", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url === "/api/run/zones") return json(ZONES(null))
      if (url === "/api/run/activities") return json({ ...RUNS, runs: [] })
      if (url.startsWith("/api/run/gap")) return json({ pace_s_per_km: 300, grade_pct: 10, gap_s_per_km: 181, cost_j_per_kg_m: 5.97, flat_cost_j_per_kg_m: 3.6, method: "Minetti et al. 2002.", confidence: "Treadmill." })
      return json({}, 404)
    })
    vi.stubGlobal("fetch", fetchMock)
    render(<RunZones />)
    expect(await screen.findByText(/No runs in the last 90 days/)).toBeTruthy()
    await userEvent.type(screen.getByLabelText("Trial 1 distance (m)"), "1200")
    await userEvent.type(screen.getByLabelText("Trial 1 time (m:ss)"), "4:00")
    await userEvent.click(screen.getByRole("button", { name: "Calculate" }))
    expect((await screen.findByRole("alert")).textContent).toContain("two or three trials")
    expect(fetchMock.mock.calls.some(([u]) => u === "/api/run/critical-speed")).toBe(false)
    await userEvent.type(screen.getByLabelText(/Pace on the slope/), "5:00")
    await userEvent.type(screen.getByLabelText("Gradient (%)"), "10")
    await userEvent.click(screen.getByRole("button", { name: "Convert" }))
    expect(await screen.findByText("Equal effort on the flat: 3:01 /km")).toBeTruthy()
    expect(fetchMock.mock.calls.some(([u]) => u === "/api/run/gap?pace_s_per_km=300&grade_pct=10")).toBe(true)
  })
})
