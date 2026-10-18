import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { Readiness } from "@/screens/Readiness"

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })
function mock(routes: Record<string, unknown>) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => (url in routes ? json(routes[url]) : json({}, 404))))
}
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

const readiness = {
  severity: "normal",
  score_0_100: 72,
  severity_reasons: [],
  readiness: { advice: "", components: { hrv: 60, tsb: 50, sleep: 70 } },
  sleep: { hrv_status: "ORANGE", sleep_h: 7.2 },
  training: { tsb: -4, source: "icu" },
}
const line = (week_load: number) => ({ ctl: 1, atl: 1, tsb: 0, week_load })

describe("Readiness across sports", () => {
  it("explains what drove the score and shows the last 7 days of load by sport", async () => {
    mock({
      "/api/readiness": readiness,
      "/api/today-session": { planned: null, adjusted: null },
      "/api/sports/load": { sports: { cycling: line(150), running: line(60) }, combined: line(210) },
    })
    render(<Readiness />)
    expect((await screen.findByText(/Today’s score used:/)).textContent).toContain("form -4 (from intervals.icu, all sports)")
    expect(await screen.findByText("Cycling: 150")).toBeTruthy()
    expect(screen.getByText("Running: 60")).toBeTruthy()
    expect(screen.getByText("All sports: 210")).toBeTruthy()
  })

  it("still shows the verdict when the sport load cannot be read", async () => {
    mock({ "/api/readiness": readiness, "/api/today-session": { planned: null, adjusted: null } })
    render(<Readiness />)
    expect(await screen.findByText("Ready to train")).toBeTruthy()
    expect(screen.queryByText("Training load, last 7 days")).toBeNull()
  })
})
