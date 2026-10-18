import { cleanup, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { bodyOf, countdown, emptyForm, raceProblem } from "@/lib/races"
import { Races } from "@/screens/Races"

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })
const taper = (over: Record<string, unknown> = {}) => ({ kind: "full", start: "2027-03-02", end: "2027-03-13", text: "Full taper over the last 12 days.", planned_tss: 410, ...over })
const A = {
  id: "plan-a", name: "Spring Fondo", date: "2027-03-14", priority: "A", discipline: "cycling", event_type: "granfondo",
  event_km: 120, event_climb_m: 1500, expected_duration_h: null, start_time: "08:30", arrive_time: null,
  in_plan: true, days_to_go: 147, taper: taper(),
}
const status = (over: Record<string, unknown> = {}) => ({
  races: [A], stored: false, has_plan: true, plan_a_date: "2027-03-14",
  taper_weeks: [{ start: "2027-03-01", end: "2027-03-07", tss_target: 300, planned_tss: 290 }],
  plan_synced: false, method: "Volume is cut and intensity kept.", confidence: "Moderate.", ...over,
})
const DAY = {
  race: A, warmup_min: 15, expected_duration_h: null, fueling: "Fueling plan comes from the Nutrition settings.",
  timeline: [{ time: "08:15", label: "Warm up (15 min)" }, { time: "08:30", label: "Start" }, { time: "13:10", label: "Expected finish" }],
  power: { available: true, ftp: 250, projected_duration_h: 4.67, if_low: 0.74, if_high: 0.76, np_low: 185, np_high: 190, predicted_np: 186, predicted_if: 0.74, predicted_tss: 258, method: "The event projection.", confidence: "Low to moderate." },
}
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe("races lib", () => {
  it("validates the form and builds the request body", () => {
    const f = { ...emptyForm(), date: "2026-10-01" }
    expect(raceProblem({ ...emptyForm() }, "2026-10-18", true)).toMatch(/date/)
    expect(raceProblem(f, "2026-10-18", true)).toMatch(/past/)
    expect(raceProblem(f, "2026-10-18", false)).toBe("")
    expect(raceProblem({ ...f, event_km: "lots" }, "2026-10-18", false)).toMatch(/Distance/)
    expect(raceProblem({ ...f, start_time: "09:00", arrive_time: "09:30" }, "2026-10-18", false)).toMatch(/Arrival/)
    expect(bodyOf({ ...f, event_km: "80", expected_duration_h: "" })).toMatchObject({ event_km: 80, expected_duration_h: null, discipline: "cycling", start_time: null })
    expect(countdown(0)).toBe("today")
    expect(countdown(3)).toBe("3 days to go")
  })
})

describe("Races", () => {
  it("adds a B race, rebuilds the plan, and shows tapers and the race-day plan", async () => {
    let current = status()
    const calls: { url: string; method: string; body: unknown }[] = []
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const method = init?.method ?? "GET"
        calls.push({ url, method, body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined })
        if (url === "/api/plan/regenerate") return json({ ok: true })
        if (url === "/api/races/plan-a/race-day") return json(DAY)
        if (url === "/api/races" && method === "POST") {
          const b = { ...A, id: "b1", name: "Club race", date: "2026-11-01", priority: "B", days_to_go: 14, taper: taper({ kind: "short", text: "Smaller taper over the last 7 days.", before_tss: 380, planned_tss: 230 }) }
          current = status({ races: [b, A], stored: true, plan_synced: true })
          return json(current)
        }
        return json(current)
      }),
    )
    render(<Races />)
    expect(await screen.findByText("Full taper over the last 12 days.")).toBeTruthy()
    expect(screen.getByText(/290/)).toBeTruthy() // the plan's taper week, planned
    const add = screen.getAllByLabelText("Name").at(-1)!
    await userEvent.type(add, "Club race")
    const dates = screen.getAllByLabelText("Date")
    await userEvent.type(dates.at(-1)!, "2026-11-01")
    await userEvent.click(screen.getByRole("button", { name: "Add race and rebuild plan" }))
    expect(await screen.findByText("Smaller taper over the last 7 days.")).toBeTruthy()
    expect(calls.find((c) => c.url === "/api/races" && c.method === "POST")!.body).toMatchObject({ name: "Club race", date: "2026-11-01", priority: "B" })
    expect(calls.some((c) => c.url === "/api/plan/regenerate")).toBe(true)

    await userEvent.click(screen.getByRole("button", { name: "Race day plan for A race: Spring Fondo" }))
    expect(await screen.findByText("185–190 W (IF 0.74–0.76)")).toBeTruthy()
    expect(screen.getByText("Fueling plan comes from the Nutrition settings.")).toBeTruthy()
    expect(screen.getByText("Warm up (15 min)")).toBeTruthy()
  })

  it("shows the server's refusal and does not rebuild", async () => {
    const urls: string[] = []
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        urls.push(url)
        if (url === "/api/races/plan-a" && init?.method === "DELETE") return json({ detail: "this A race is your plan's goal: build a new plan to change it" }, 400)
        return json(status())
      }),
    )
    render(<Races />)
    await userEvent.click(await screen.findByRole("button", { name: "Delete A race: Spring Fondo" }))
    expect((await screen.findByRole("alert")).textContent).toMatch(/plan's goal/)
    expect(urls).not.toContain("/api/plan/regenerate")
  })
})
