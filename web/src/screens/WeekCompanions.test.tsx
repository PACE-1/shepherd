import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { isoDay } from "@/lib/home"
import { CompanionToday } from "@/screens/CompanionToday"
import { WeekCompanions } from "@/screens/WeekCompanions"

const today = isoDay()
const note = "Not validated against real runs/swims yet."
const comp = (over = {}) => ({
  id: `running-${today}`, day: today, day_name: "", sport: "running", session_type: "run_easy", duration_min: 45,
  description: "Easy aerobic run at a conversational effort.", status: "pending", hard: false, template_id: "t", workout: null, dismissed_at: "",
  ...over,
})
const body = (companions: unknown[], todayList: unknown[] = companions) => ({
  enabled: true, has_plan: true, note, today: todayList, weeks: [{ week_num: 1, start: "2026-10-12", end: "2026-10-18", companions }],
})
const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe("WeekCompanions", () => {
  it("lists the week's companions with the not-validated label and dismisses one", async () => {
    const calls: string[] = []
    let dismissed = false
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      calls.push(`${init?.method ?? "GET"} ${url}`)
      if (url.endsWith("/dismiss")) {
        dismissed = true
        return json({ ok: true, companion: comp({ status: "dismissed" }) })
      }
      return json(body([comp({ status: dismissed ? "dismissed" : "pending" }), comp({ id: "swimming-x", sport: "swimming", duration_min: 30, status: "done" })]))
    }))
    render(<WeekCompanions start="2026-10-12" />)
    expect(await screen.findByText("Run")).toBeTruthy()
    expect(screen.getByText("Swim")).toBeTruthy()
    expect(screen.getByText(note)).toBeTruthy()
    expect(screen.getByText(/30 min · done/)).toBeTruthy()
    expect(calls[0]).toBe("GET /api/plan/companions?start=2026-10-12")
    fireEvent.click(screen.getByRole("button", { name: /Dismiss Run/ }))
    await waitFor(() => expect(screen.getByText(/45 min · dismissed/)).toBeTruthy())
    expect(calls).toContain(`POST /api/plan/companions/${encodeURIComponent(`running-${today}`)}/dismiss`)
  })

  it("renders nothing for a week without companions or on an error", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json(body([]))))
    const { container } = render(<WeekCompanions start="2026-10-12" />)
    await waitFor(() => expect(container.innerHTML).toBe(""))
    cleanup()
    vi.stubGlobal("fetch", vi.fn(async () => json({}, 500)))
    const again = render(<WeekCompanions start="2026-10-12" />)
    await new Promise((r) => setTimeout(r, 0))
    expect(again.container.innerHTML).toBe("")
  })
})

describe("CompanionToday", () => {
  it("shows today's companion with the label", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json(body([comp()]))))
    render(<CompanionToday />)
    expect(await screen.findByText("Run")).toBeTruthy()
    expect(screen.getByText(/45 min/)).toBeTruthy()
    expect(screen.getByText(note)).toBeTruthy()
  })

  it("renders nothing without one", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json(body([comp()], []))))
    const { container } = render(<CompanionToday />)
    await new Promise((r) => setTimeout(r, 0))
    expect(container.innerHTML).toBe("")
  })
})
