import { cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { isoDay } from "@/lib/home"
import { Home } from "@/screens/Home"

const today = isoDay()
const addDays = (n: number) => {
  const d = new Date()
  d.setDate(d.getDate() + n)
  return isoDay(d)
}
const session = (day: string, over = {}) => ({
  day, day_name: "Day", session_type: "z2", duration_min: 80, tss_estimate: 48.2, description: "", zwo_name: "Endurance Steady", status: "pending", ...over,
})
const PLAN = {
  plan_json: {
    goal: {}, phases: [],
    weeks: [{ week_num: 1, start: addDays(-2), end: addDays(4), phase: "base", tss_target: 300, is_stepback: false,
      sessions: [session(today), session(addDays(1), { session_type: "threshold", duration_min: 60, tss_estimate: 70 })] }],
  },
}
const STATS = { errors: [], power: { ftp: { value: 265 }, w_per_kg: { value: 3.5 } }, load: { ctl: { value: null }, atl: { value: 40 }, tsb: { value: null } } }
const SUMMARY = { weeks: 12, rides: 5, totals: { hours: 20.5, km: 400 } }

function mockApi(over: Record<string, () => Response> = {}) {
  const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })
  const calls: string[] = []
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    calls.push(url)
    if (over[url]) return over[url]()
    if (url === "/api/plan") return json(PLAN)
    if (url === "/api/rider-stats") return json(STATS)
    if (url === "/api/programme/summary") return json(SUMMARY)
    if (url === "/api/readiness") return json({ severity: "normal", score_0_100: 80, severity_reasons: [] })
    if (url === "/api/today-session") return json({ planned: null, adjusted: null, was_modified: false })
    if (url.startsWith("/api/profile/pr-toast-queue")) return json({ queue: [], count: 0 })
    if (url.startsWith("/api/metrics/history")) return json([])
    if (url === "/api/wellness/hrv-recording-status") return json({ should_show_prompt: false })
    if (url === "/api/daily-log") return json({ today: null, history: [] })
    if (url === "/api/profile/dfa-alpha1") return json({ value: 0.87, n_rides: 3, last_computed_at: "2026-10-12T08:00:00", n_recent_total: 5, n_no_rr_data: 2, n_fetch_failed: 0, message: "" })
    if (url.startsWith("/api/week-summary")) return json({ week_start: "2026-10-12", week_end: "2026-10-18", tss_target: null, tss_done: 0, sports: {} })
    return json({}, 404)
  }))
  return calls
}

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe("Home", () => {
  it("shows the latest DFA α1", async () => {
    mockApi()
    render(<Home />)
    expect(await screen.findByText(/from 3 recent rides, last computed 2026-10-12/)).toBeTruthy()
  })

  it("shows today's session, the week's planned load, fitness and the programme", async () => {
    mockApi()
    render(<Home />)
    expect((await screen.findAllByText("Endurance Steady")).length).toBeGreaterThan(0)
    expect(screen.getByText(/118 of 300 TSS planned/)).toBeTruthy()
    expect(screen.getByText("265 W")).toBeTruthy()
    expect(screen.getAllByText("—").length).toBe(2) // CTL and TSB have no reading
    expect(screen.getByText("40")).toBeTruthy()
    expect(screen.getByText("20.5")).toBeTruthy()
  })

  it("says so when there is no plan", async () => {
    mockApi({ "/api/plan": () => new Response(JSON.stringify({ plan_json: { goal: {}, phases: [], weeks: [] } })) })
    render(<Home />)
    expect(await screen.findByText(/No training plan yet/)).toBeTruthy()
  })

  it("shows a rest day when nothing is planned today", async () => {
    const week = PLAN.plan_json.weeks[0]
    mockApi({ "/api/plan": () => new Response(JSON.stringify({ plan_json: { ...PLAN.plan_json, weeks: [{ ...week, sessions: [session(addDays(1))] }] } })) })
    render(<Home />)
    expect(await screen.findByText(/Rest day/)).toBeTruthy()
  })

  it("a failing card says so and retries on its own", async () => {
    let fail = true
    const calls = mockApi({
      "/api/rider-stats": () => (fail ? new Response(JSON.stringify({ error: "boom" }), { status: 500 }) : new Response(JSON.stringify(STATS))),
    })
    render(<Home />)
    const alert = await screen.findByRole("alert")
    expect(alert.textContent).toContain("boom")
    expect((await screen.findAllByText("Endurance Steady")).length).toBeGreaterThan(0) // other cards still work
    fail = false
    const before = calls.filter((u) => u === "/api/plan").length
    await userEvent.click(screen.getByRole("button", { name: "Retry" }))
    await waitFor(() => expect(screen.getByText("265 W")).toBeTruthy())
    expect(calls.filter((u) => u === "/api/plan").length).toBe(before) // only the failed card refetched
  })
})
