import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { parseRaceTime, raceTime } from "@/lib/predict"
import { RacePredictor } from "@/screens/RacePredictor"

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })
const row = (race: string, label: string, model: string, status: string, time_s: number | null, extra = {}) =>
  ({ race, label, distance_m: 0, model, status, time_s, pace_s_per_km: time_s ? 290 : null, range_text: null, notes: [], ...extra })
const BASE = { window_days: 56, riegel_method: "Riegel 1981.", riegel_confidence: "Vickers and Vertosick 2016.", cs_method: "CS model.", cs_confidence: "2 to 30 minutes.", long_run_rule: "Heuristic." }
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe("raceTime", () => {
  it("reads minutes and hours", () => {
    expect([raceTime(1190), raceTime(11509.3), raceTime(3600), raceTime(59.6)]).toEqual(["19:50", "3:11:49", "1:00:00", "1:00"])
  })
})

describe("RacePredictor", () => {
  it("shows each prediction with its input, model and caveats", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => url === "/api/run/predict" ? json({
      ...BASE,
      best_run: { id: "r1", date: "2026-10-15", name: "Tempo", distance_m: 10000, time_s: 2900, pace_s_per_km: 290 },
      longest_run_m: 12000,
      critical_speed: { cs_m_per_s: 4, d_prime_m: 240, date: "2026-10-10" },
      predictions: [
        row("10k", "10K", "riegel", "ok", 2900),
        row("half", "Half marathon", "riegel", "ok", 6398.6, { notes: ["Assumes specific endurance training for this distance (regular long runs)."] }),
        row("marathon", "Marathon", "riegel", "not_enough_long_run", null, { notes: ["Not enough long-run history: 12.0 km (heuristic)."] }),
        row("5k", "5K", "critical_speed", "ok", 1190),
        row("10k", "10K", "critical_speed", "out_of_range", null),
        row("marathon", "Marathon", "critical_speed", "not_supported", null),
      ],
      missing: [],
    }) : json({}, 404)))
    render(<RacePredictor />)
    const riegel = await screen.findByRole("table", { name: "Riegel predictions" })
    expect(screen.getByText(/Input: Tempo on 2026-10-15, 10.0 km in 48:20/)).toBeTruthy()
    expect(screen.getByText(/Longest run in 8 weeks: 12.0 km/)).toBeTruthy()
    expect(within(riegel).getByText("1:46:39 (4:50 /km)")).toBeTruthy()
    expect(within(riegel).getByText(/specific endurance training/)).toBeTruthy()
    expect(within(riegel).getByText("Not enough long-run history")).toBeTruthy()
    const cs = screen.getByRole("table", { name: "Critical-speed predictions" })
    expect(screen.getByText(/critical speed 4:10 \/km, D′ 240 m, test saved 2026-10-10/)).toBeTruthy()
    expect(within(cs).getByText(/^19:50/)).toBeTruthy()
    expect(within(cs).getByText("Outside the model's range")).toBeTruthy()
    expect(within(cs).getByText("Not supported by this model")).toBeTruthy()
    expect(screen.getByText(/Vickers and Vertosick 2016/)).toBeTruthy()
  })

  it("says what is missing when there is no input", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json({ ...BASE, predictions: [], missing: ["No run of 3 km or more in the window, so there is no Riegel prediction."] })))
    render(<RacePredictor />)
    expect(await screen.findByText(/No run of 3 km or more/)).toBeTruthy()
    expect(screen.queryByRole("table")).toBeNull()
  })

  it("asks for a target and shows how far each model is from it", async () => {
    const fetchMock = vi.fn(async (url: string) => json({
      ...BASE, predictions: [], missing: [],
      best_run: { id: "r1", date: "2026-10-15", name: "Tempo", distance_m: 10000, time_s: 2900, pace_s_per_km: 290 },
      critical_speed: { cs_m_per_s: 4, d_prime_m: 240, date: "2026-10-10" },
      target: url.includes("target_race=5k&target_time_s=1190")
        ? { race: "5k", target_time_s: 1190, riegel: { needed_time_s: 2800, current_time_s: 2900, faster_pct: 3.4 }, critical_speed: { needed_cs_m_per_s: 4.2, current_cs_m_per_s: 4, higher_pct: 5 } }
        : null,
    }))
    vi.stubGlobal("fetch", fetchMock)
    render(<RacePredictor />)
    const input = await screen.findByLabelText("Target time", { selector: "input" })
    fireEvent.change(input, { target: { value: "19:50" } })
    fireEvent.click(screen.getByRole("button", { name: "Check" }))
    const gap = await screen.findByLabelText("Target gap")
    expect(within(gap).getByText(/best recent run would have to be 3.4% faster \(48:20 to 46:40\) to predict 19:50/)).toBeTruthy()
    expect(within(gap).getByText(/Critical speed: it would have to be 5% higher/)).toBeTruthy()
    expect(fetchMock).toHaveBeenCalledWith("/api/run/predict?target_race=5k&target_time_s=1190", expect.anything())
  })

  it("rejects a target that is not a time without calling the API again", async () => {
    const fetchMock = vi.fn(async () => json({ ...BASE, predictions: [], missing: [] }))
    vi.stubGlobal("fetch", fetchMock)
    render(<RacePredictor />)
    fireEvent.change(await screen.findByLabelText("Target time", { selector: "input" }), { target: { value: "fast" } })
    fireEvent.click(screen.getByRole("button", { name: "Check" }))
    expect(await screen.findByRole("alert")).toBeTruthy()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it("reads again when a critical-speed save bumps refreshKey", async () => {
    const fetchMock = vi.fn(async () => json({ ...BASE, predictions: [], missing: [] }))
    vi.stubGlobal("fetch", fetchMock)
    const { rerender } = render(<RacePredictor refreshKey={0} />)
    await screen.findByLabelText("Target time", { selector: "input" })
    rerender(<RacePredictor refreshKey={1} />)
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
  })
})

describe("parseRaceTime", () => {
  it("reads m:ss and h:mm:ss, nothing else", () => {
    expect([parseRaceTime("19:50"), parseRaceTime("1:46:39"), parseRaceTime("0:00"), parseRaceTime("fast"), parseRaceTime("19:75")]).toEqual([1190, 6399, null, null, null])
  })
})
