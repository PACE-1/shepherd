import { cleanup, render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { parseTemp, per100, waterLabel } from "@/lib/swim"
import { SwimZones } from "@/screens/SwimZones"

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })
const CSS = (v: number | null) => ({
  css_s_per_100m: v,
  history: v ? [{ value: v, date: "2026-10-18", source: "css_test" }] : [],
  zones_note: "Swim pace zones are not shown.",
  method: "Wakayoshi et al. 1993.",
  confidence: "Two swims fit the line exactly.",
})
const TEST = (saved: boolean) => ({ css_m_per_s: 1.053, css_s_per_100m: 95, anaerobic_distance_m: 21.1, r2: null, n_trials: 2, method: "Wakayoshi.", confidence: "Exact fit.", saved })
const SWIMS = (stss: number | null) => ({
  css_s_per_100m: stss ? 95 : null,
  swims: [
    { id: "s1", date: "2026-10-17", name: "Pool set", type: "Swim", water: "pool", duration_s: 2000, distance_m: 2000, pace_s_per_100m: 100, stss, icu_load: 40, pool_length_m: 25, lengths: 80, stroke_rate: 30 },
    { id: "s2", date: "2026-10-16", name: "Lake", type: "OpenWaterSwim", water: "open_water", duration_s: 3600, distance_m: 3000, pace_s_per_100m: 120, stss: null, icu_load: 50, pool_length_m: null, lengths: null, stroke_rate: null },
  ],
  missing: stss ? [] : ["Set a swim CSS, or save a CSS test, to get sTSS."],
  method: "sTSS.",
  confidence: "Average speed.",
  stroke_note: "No SWOLF.",
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe("swim text", () => {
  it("formats pace, where, and water temperature", () => {
    expect(per100(95)).toBe("1:35 /100 m")
    expect([waterLabel("pool", 25), waterLabel("pool", null), waterLabel("open_water", null), waterLabel("unknown", 25)]).toEqual(["Pool 25 m", "Pool", "Open water", "–"])
    expect([parseTemp(""), parseTemp("16.5"), parseTemp("16,5"), parseTemp("-1"), parseTemp("warm")]).toEqual([null, 16.5, 16.5, -1, undefined])
  })
})

describe("SwimZones", () => {
  it("computes CSS from 400 m and 200 m, saves it, and the swims get sTSS", async () => {
    let css: number | null = null
    const posts: unknown[] = []
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/swim/css") return json(CSS(css))
      if (url === "/api/swim/activities") return json(SWIMS(css ? 61.7 : null))
      if (url === "/api/swim/open-water") return json({ notes: [] })
      if (url === "/api/swim/css-test") {
        const body = JSON.parse(init!.body as string)
        posts.push(body)
        if (body.save) css = 95
        return json(TEST(body.save))
      }
      return json({}, 404)
    }))
    render(<SwimZones />)
    expect(await screen.findByText(/No swim CSS yet/)).toBeTruthy()
    expect(screen.getByText("Swim pace zones are not shown.")).toBeTruthy()
    const table = await screen.findByRole("table", { name: "Recent swims" })
    expect(within(table).getByText("Pool 25 m")).toBeTruthy()
    expect(within(table).getByText("Open water")).toBeTruthy()
    expect(within(table).getByText("30 /min")).toBeTruthy()
    expect(screen.getByText(/to get sTSS/)).toBeTruthy()
    await userEvent.type(screen.getByLabelText("Swim 1 time (m:ss)"), "6:00")
    await userEvent.type(screen.getByLabelText("Swim 2 time (m:ss)"), "2:50")
    await userEvent.click(screen.getByRole("button", { name: "Work out CSS" }))
    expect(await screen.findByText(/CSS 1:35 \/100 m \(1.053 m\/s\)/)).toBeTruthy()
    expect(posts[0]).toEqual({ trials: [{ distance_m: 400, time_s: 360 }, { distance_m: 200, time_s: 170 }], save: false })
    await userEvent.click(screen.getByRole("button", { name: "Use as swim CSS" }))
    expect((await screen.findByRole("status")).textContent).toContain("Saved 1:35 /100 m")
    expect(await screen.findByRole("table", { name: "CSS history" })).toBeTruthy()
    expect(await within(screen.getByRole("table", { name: "Recent swims" })).findByText("62")).toBeTruthy()
  })

  it("refuses a missing time without calling the server", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url === "/api/swim/css") return json(CSS(null))
      if (url === "/api/swim/activities") return json({ ...SWIMS(null), swims: [] })
      if (url === "/api/swim/open-water") return json({ notes: [] })
      return json({}, 404)
    })
    vi.stubGlobal("fetch", fetchMock)
    render(<SwimZones />)
    expect(await screen.findByText(/No swims in the last 90 days/)).toBeTruthy()
    await userEvent.type(screen.getByLabelText("Swim 1 time (m:ss)"), "6:00")
    await userEvent.click(screen.getByRole("button", { name: "Work out CSS" }))
    expect((await screen.findByRole("alert")).textContent).toContain("Enter both swims")
    expect(fetchMock.mock.calls.some(([u]) => u === "/api/swim/css-test")).toBe(false)
  })
})
