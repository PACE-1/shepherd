import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import type { PlanRead, RiderStats } from "@/api/types"
import { isoDay } from "@/lib/home"
import { Glance } from "@/screens/Glance"

const today = isoDay()
const addDays = (n: number) => {
  const d = new Date()
  d.setDate(d.getDate() + n)
  return isoDay(d)
}
const session = (day: string, over = {}) => ({
  day, day_name: "Day", session_type: "threshold", duration_min: 60, tss_estimate: 70, description: "", zwo_name: "Hard Intervals", status: "pending", ...over,
})
const plan = (sessions: unknown[]) =>
  ({ state: "ok", data: { plan_json: { goal: {}, phases: [], weeks: [{ week_num: 1, start: addDays(-3), end: addDays(3), phase: "base", tss_target: 300, is_stepback: false, sessions }] } } }) as unknown as { state: "ok"; data: PlanRead }
const stats = (tsb: number | null) => ({ state: "ok", data: { errors: [], load: { tsb: { value: tsb } } } }) as unknown as { state: "ok"; data: RiderStats }

function mockApi(routes: Record<string, unknown> = {}) {
  const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })
  const all: Record<string, unknown> = {
    "/api/readiness": { severity: "normal", score_0_100: 80, severity_reasons: [] },
    "/api/week-summary?week_offset=0": { week_start: "", week_end: "", planned_days_done: 1 },
    "/api/icu/connection": { connected: true, method: "apikey" },
    "/api/settings": { lthr_is_set: true },
    ...routes,
  }
  vi.stubGlobal("fetch", vi.fn(async (url: string) => (url in all ? json(all[url]) : json({}, 404))))
}
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe("Glance", () => {
  it("says ready, shows today's session in plain words and this week's progress", async () => {
    mockApi()
    render(<Glance plan={plan([session(today), session(addDays(1)), session(addDays(-1), { status: "done" })])} stats={stats(-5)} />)
    expect(await screen.findByText("Ready to train")).toBeTruthy()
    expect(screen.getByText("Hard Intervals")).toBeTruthy()
    expect(screen.getByText("hard intervals near your limit")).toBeTruthy()
    expect(await screen.findByText(/of 3 planned rides done/)).toBeTruthy()
    expect(screen.getByText(/Form score -5: your fitness minus your tiredness/)).toBeTruthy()
    expect(screen.queryByText(/Next step/)).toBeNull()
  })

  it("says rest when readiness says rest", async () => {
    mockApi({ "/api/readiness": { severity: "rest", score_0_100: 20, severity_reasons: [] } })
    render(<Glance plan={plan([session(today)])} stats={stats(0)} />)
    expect(await screen.findByText("Rest today")).toBeTruthy()
  })

  it("shows a rest day with no session and takes it easy when readiness is reduced", async () => {
    mockApi({ "/api/readiness": { severity: "tier_down", score_0_100: 50, severity_reasons: [] } })
    render(<Glance plan={plan([session(addDays(1))])} stats={stats(0)} />)
    expect(await screen.findByText("Rest today")).toBeTruthy() // the plan's rest day comes before easing
    expect(screen.getByText(/No ride planned/)).toBeTruthy()
  })

  it("points to one next step when setup is incomplete", async () => {
    mockApi({ "/api/icu/connection": { connected: false } })
    render(<Glance plan={plan([session(today)])} stats={stats(0)} />)
    const link = await screen.findByRole("link", { name: "Connect intervals.icu" })
    expect(link.getAttribute("href")).toBe("#/onboarding")
  })

  it("stays useful when the other reads fail", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 500 })))
    render(<Glance plan={plan([session(today)])} stats={stats(null)} />)
    expect(await screen.findByText("Not enough data yet")).toBeTruthy()
    expect(screen.getByText("Hard Intervals")).toBeTruthy()
    expect(screen.queryByText(/Next step/)).toBeNull() // unreadable means no nagging
  })

  it("says so when there is no plan", async () => {
    mockApi({})
    render(<Glance plan={{ state: "ok", data: { plan_json: { goal: {}, phases: [], weeks: [] } } as unknown as PlanRead }} stats={stats(null)} />)
    expect(await screen.findByRole("link", { name: "Create a training plan" })).toBeTruthy()
    expect(screen.getByText(/No training plan covers today/)).toBeTruthy()
  })
})
