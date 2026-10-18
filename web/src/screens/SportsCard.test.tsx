import { cleanup, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { parseClock } from "@/lib/sports"
import { SportsCard } from "@/screens/SportsCard"

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })
const line = (ctl: number) => ({ ctl, atl: 30, tsb: -5, week_load: 200 })
const LOAD = { as_of: "2026-10-18", days_of_history: 60, settled: false, combined: line(70), sports: { cycling: line(50), running: line(20) }, method: "m", confidence: "Approximation across sports." }
const THR = (css: number | null) => ({ thresholds: {
  run_threshold_pace: { sport: "running", unit: "s/km", current: 270, history: [] },
  run_threshold_hr: { sport: "running", unit: "bpm", current: null, history: [] },
  swim_css: { sport: "swimming", unit: "s/100m", current: css, history: [] },
} })
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe("parseClock", () => {
  it("reads m:ss or seconds and refuses anything else", () => {
    expect([parseClock("4:30"), parseClock("270"), parseClock("4:75"), parseClock("fast")]).toEqual([270, 270, null, null])
  })
})

describe("SportsCard", () => {
  it("shows load per sport and saves a swim threshold typed as m:ss", async () => {
    let css: number | null = null
    const calls: { url: string; body: unknown }[] = []
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined })
      if (url === "/api/sports/load") return json(LOAD)
      if (init?.method === "POST") { css = 95; return json(THR(css)) }
      return json(THR(css))
    }))
    render(<SportsCard />)
    expect(await screen.findByText("Running")).toBeTruthy()
    expect(screen.getByText("All sports")).toBeTruthy()
    expect(screen.getByText(/still settling/)).toBeTruthy()
    expect(screen.getByText("Now 4:30 /km")).toBeTruthy()
    await userEvent.type(screen.getByLabelText(/Swim critical speed/), "1:35")
    await userEvent.click(screen.getAllByRole("button", { name: "Set" })[2])
    expect(await screen.findByText("Now 1:35 /100 m")).toBeTruthy()
    expect(calls.find((c) => c.url === "/api/sports/thresholds" && c.body)!.body).toEqual({ kind: "swim_css", value: 95 })
  })

  it("explains a malformed value without calling the server", async () => {
    const fetchMock = vi.fn(async (url: string) => json(url === "/api/sports/load" ? LOAD : THR(null)))
    vi.stubGlobal("fetch", fetchMock)
    render(<SportsCard />)
    await userEvent.type(await screen.findByLabelText(/Run threshold heart rate/), "fast")
    await userEvent.click(screen.getAllByRole("button", { name: "Set" })[1])
    expect((await screen.findByRole("alert")).textContent).toContain("whole number")
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})
