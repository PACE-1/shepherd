import { cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { episodeProblem } from "@/lib/injury"
import { Injury } from "@/screens/Injury"

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })
const EP = { id: "e1", type: "illness", start: "2026-10-10", end: null, sport: "all", body_area: "", note: "flu" }
const status = (over: Record<string, unknown> = {}) => ({
  episodes: [],
  active: null,
  return_ramp: null,
  ramp_weeks: [],
  has_plan: true,
  plan_synced: false,
  method: "The planner's absence ramp.",
  note: "Not medical advice.",
  ...over,
})
const line = (week_load: number, prev: number, level: string, change_pct: number | null) => ({ week_load, prev_4wk_avg: prev, ratio: null, change_pct, level })
const RAMP = {
  as_of: "2026-10-18",
  threshold: 1.3,
  high: 1.5,
  combined: line(400, 280, "elevated", 43),
  sports: { cycling: line(300, 260, "ok", 15), running: line(100, 20, "high", 400) },
  warn: true,
  warnings: ["All sports: this week's load is 43% above your 4-week average (400 vs 280)."],
  method: "Uncoupled ratio.",
  confidence: "Low.",
  note: "Not medical advice.",
}
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe("episodeProblem", () => {
  it("needs a first day and an end not before it", () => {
    expect(episodeProblem({ start: "", end: "" })).toMatch(/first day/)
    expect(episodeProblem({ start: "2026-10-10", end: "2026-10-09" })).toMatch(/before/)
    expect(episodeProblem({ start: "2026-10-10", end: "" })).toBe("")
  })
})

describe("Injury", () => {
  it("records an episode, rebuilds the plan, and shows the advice note and the ramp warning", async () => {
    let current = status()
    const calls: { url: string; method: string; body: unknown }[] = []
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        calls.push({ url, method: init?.method ?? "GET", body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined })
        if (url === "/api/injury/ramp-rate") return json(RAMP)
        if (url === "/api/plan/regenerate") return json({ ok: true })
        if (url === "/api/injury/episodes") {
          current = status({ episodes: [EP], active: EP, plan_synced: true })
          return json(current)
        }
        return json(current)
      }),
    )
    render(<Injury />)
    expect(screen.getByRole("note").textContent).toMatch(/Not medical advice.*fever or chest symptoms/)
    expect(await screen.findByText(/43% above your 4-week average/)).toBeTruthy()
    expect(screen.getByText("+400% (Spike)")).toBeTruthy()
    await userEvent.type(screen.getByLabelText("Note"), "flu")
    await userEvent.click(screen.getByRole("button", { name: "Save" }))
    expect(await screen.findByText(/Now: Illness, All sports: 2026-10-10 to ongoing/)).toBeTruthy()
    expect(screen.getByText(/The plan is paused/)).toBeTruthy()
    const post = calls.find((c) => c.url === "/api/injury/episodes")!
    expect(post.body).toMatchObject({ type: "illness", sport: "all", note: "flu", body_area: "" })
    expect(calls.some((c) => c.url === "/api/plan/regenerate")).toBe(true)
  })

  it("'I'm back' resolves the open episode and shows the return ramp", async () => {
    let current = status({ episodes: [EP], active: EP })
    const urls: string[] = []
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        urls.push(url)
        if (url === "/api/injury/ramp-rate") return json({ ...RAMP, warn: false, warnings: [] })
        if (url.endsWith("/resolve")) {
          current = status({
            episodes: [{ ...EP, end: "2026-10-17" }],
            return_ramp: { episode_id: "e1", type: "illness", start: "2026-10-10", end: "2026-10-17", episode_days: 8, absence_days: 8, weeks_done: 0 },
            ramp_weeks: [{ start: "2026-10-18", end: "2026-10-24", phase: "recon", tss_target: 240, easy_only: true }],
            plan_synced: false,
          })
          return json(current)
        }
        return json(current)
      }),
    )
    render(<Injury />)
    expect(await screen.findByText(/No sport is ramping faster than 30%/)).toBeTruthy()
    await userEvent.click(await screen.findByRole("button", { name: "I'm back" }))
    expect(await screen.findByText(/Back after 8 days of illness/)).toBeTruthy()
    expect(screen.getByText("Easy only")).toBeTruthy()
    expect(urls).toContain("/api/injury/episodes/e1/resolve")
    expect(urls).not.toContain("/api/plan/regenerate")
  })

  it("shows the server's refusal", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url === "/api/injury/ramp-rate") return json(RAMP)
        if (init?.method === "POST") return json({ detail: "end must not be before start" }, 400)
        return json(status())
      }),
    )
    render(<Injury />)
    await userEvent.click(await screen.findByRole("button", { name: "Save" }))
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("end must not be before start"))
  })
})
