import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { companionLabel, fmtClock, parseClock } from "@/lib/companions"
import { isoDay } from "@/lib/home"
import { WeekCompanions } from "@/screens/WeekCompanions"

const today = isoDay()
const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })
const comp = (over = {}) => ({
  id: `running-${today}`, day: today, day_name: "", sport: "running", session_type: "brick_run", duration_min: 20,
  description: "Brick: a short easy run straight after the ride.", status: "pending", hard: false, template_id: "t",
  workout: null, dismissed_at: "", brick_of: `cycling-${today}`, ...over,
})
const body = (companions: unknown[], target: number | null = null) => ({
  enabled: true, has_plan: true, note: "Not validated against real runs/swims yet.", today: companions, transition_target_s: target,
  weeks: [{ week_num: 1, start: "2026-10-12", end: "2026-10-18", companions }],
})

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe("companions lib: bricks and labels", () => {
  it("parses and formats transition times and labels bricks and mobility", () => {
    expect(parseClock("2:30")).toBe(150)
    expect(parseClock("90")).toBe(90)
    expect(parseClock("")).toBeNull()
    expect(parseClock("0:00")).toBeUndefined()
    expect(parseClock("2:75")).toBeUndefined()
    expect(parseClock("61:00")).toBeUndefined()
    expect(fmtClock(150)).toBe("2:30")
    const base = comp({ brick_of: null, session_type: "run_easy" })
    expect(companionLabel(comp())).toBe("Brick run")
    expect(companionLabel({ ...base, sport: "strength", session_type: "mobility" })).toBe("Mobility")
    expect(companionLabel({ ...base, sport: "strength", session_type: "strength" })).toBe("Strength")
    expect(companionLabel(base)).toBe("Run")
  })
})

describe("WeekCompanions: bricks and the limiter tag", () => {
  it("shows a brick with no default target, saves the rider's target and note", async () => {
    const calls: { url: string; method: string; body: unknown }[] = []
    let target: number | null = null
    let note = ""
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET"
      const b = typeof init?.body === "string" ? JSON.parse(init.body) : undefined
      calls.push({ url, method, body: b })
      if (url === "/api/plan/bricks/transition") {
        target = b.transition_target_s
        return json({ ok: true, transition_target_s: target })
      }
      if (url.endsWith("/brick-note")) {
        note = b.note
        return json({ ok: true, companion: comp({ brick_note: note }) })
      }
      return json(body([comp({ brick_note: note || null }), comp({ id: "swimming-x", sport: "swimming", session_type: "swim_css", brick_of: null, hard: true, limiter: "Your limiter: first pick of the week's hard-session slots." })], target))
    }))
    render(<WeekCompanions start="2026-10-12" />)
    expect(await screen.findByText("Brick run")).toBeTruthy()
    expect(screen.getByText(/No transition target set/)).toBeTruthy()
    expect(screen.getByText("Your limiter: first pick of the week's hard-session slots.")).toBeTruthy()

    const input = screen.getByLabelText("Transition target (m:ss)")
    fireEvent.change(input, { target: { value: "2:99" } })
    expect((screen.getByRole("button", { name: "Save target" }) as HTMLButtonElement).disabled).toBe(true)
    fireEvent.change(input, { target: { value: "2:30" } })
    fireEvent.click(screen.getByRole("button", { name: "Save target" }))
    await waitFor(() => expect(screen.getByText(/Your transition target: 2:30/)).toBeTruthy())
    expect(calls.find((c) => c.method === "PUT")!.body).toEqual({ transition_target_s: 150 })

    fireEvent.change(screen.getByLabelText("How did the run feel off the bike?"), { target: { value: "Heavy legs, then fine." } })
    fireEvent.click(screen.getByRole("button", { name: "Save note" }))
    await waitFor(() => expect(calls.some((c) => c.url === `/api/plan/companions/${encodeURIComponent(`running-${today}`)}/brick-note`)).toBe(true))
    expect(calls.find((c) => c.url.endsWith("/brick-note"))!.body).toEqual({ note: "Heavy legs, then fine." })
  })

  it("asks for the note only once the brick's day has come", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json(body([comp({ day: "2999-01-01" })], 120))))
    render(<WeekCompanions start="2026-10-12" />)
    expect(await screen.findByText(/Your transition target: 2:00/)).toBeTruthy()
    expect(screen.queryByLabelText("How did the run feel off the bike?")).toBeNull()
  })
})
