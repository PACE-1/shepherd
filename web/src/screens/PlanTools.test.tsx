import { cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { isoDay } from "@/lib/home"
import { Plan } from "@/screens/Plan"
import { PlanAvailability } from "@/screens/PlanAvailability"
import { PlanRace } from "@/screens/PlanRace"
import { PlanRedraw } from "@/screens/PlanRedraw"
import { PlanRematch } from "@/screens/PlanRematch"

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })
type Handler = (body: unknown) => Response
function mock(routes: Record<string, Handler>) {
  const calls: { url: string; body: unknown }[] = []
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const body = init?.body ? JSON.parse(init.body as string) : undefined
    calls.push({ url, body })
    if (url === "/api/event/projection" && !routes[url]) return json({ available: false })
    return (routes[url] ?? (() => json({}, 404)))(body)
  }))
  return calls
}
const addDays = (n: number) => {
  const d = new Date()
  d.setDate(d.getDate() + n)
  return isoDay(d)
}
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe("PlanAvailability", () => {
  it("sends the whole map: edits applied, blanks removed, other weeks kept", async () => {
    const calls = mock({ "/api/plan/save-availability": () => json({ ok: true }) })
    const onDone = vi.fn()
    const start = addDays(0)
    const stored = { [addDays(0)]: { hours: 2, type: "available" }, [addDays(1)]: { hours: 1, type: "available" }, "2030-01-01": { hours: 3, type: "available" } }
    render(<PlanAvailability weekStart={start} today={start} stored={stored} onDone={onDone} onCancel={() => {}} />)
    const inputs = screen.getAllByRole("spinbutton") as HTMLInputElement[]
    await userEvent.clear(inputs[0])
    await userEvent.clear(inputs[1])
    await userEvent.type(inputs[1], "0")
    await userEvent.click(screen.getByRole("button", { name: "Save availability" }))
    await waitFor(() => expect(onDone).toHaveBeenCalled())
    expect(calls[0].body).toEqual({ availability: { [addDays(1)]: { hours: 0, type: "holiday" }, "2030-01-01": { hours: 3, type: "available" } } })
  })

  it("refuses hours outside 0 to 12", async () => {
    mock({})
    const start = addDays(0)
    render(<PlanAvailability weekStart={start} today={start} stored={{}} onDone={() => {}} onCancel={() => {}} />)
    await userEvent.type(screen.getAllByRole("spinbutton")[0], "20")
    expect((screen.getByRole("button", { name: "Save availability" }) as HTMLButtonElement).disabled).toBe(true)
  })
})

describe("PlanRace", () => {
  it("adds a race with its priority", async () => {
    const calls = mock({ "/api/plan/add-race": () => json({ ok: true }) })
    const onDone = vi.fn()
    render(<PlanRace onDone={onDone} onCancel={() => {}} />)
    await userEvent.type(screen.getByLabelText("Race date"), addDays(30))
    await userEvent.type(screen.getByLabelText("Name"), "Crit")
    await userEvent.selectOptions(screen.getByLabelText("Priority"), "C")
    await userEvent.click(screen.getByRole("button", { name: "Add race and reshape plan" }))
    await waitFor(() => expect(onDone).toHaveBeenCalled())
    expect(calls[0].body).toEqual({ date: addDays(30), name: "Crit", priority: "C" })
  })

  it("shows the server's refusal", async () => {
    mock({ "/api/plan/add-race": () => json({ error: "race date is in the past" }, 400) })
    render(<PlanRace onDone={() => {}} onCancel={() => {}} />)
    await userEvent.type(screen.getByLabelText("Race date"), addDays(5))
    await userEvent.click(screen.getByRole("button", { name: "Add race and reshape plan" }))
    expect((await screen.findByRole("alert")).textContent).toContain("race date is in the past")
  })
})

describe("PlanRedraw", () => {
  const cand = (name: string) => ({ ok: true, day: "2026-10-20", zwo_file: `${name}.zwo`, zwo_name: name, variation: 1, duration_min: 60, tss_estimate: 55 })

  it("previews, asks for another without repeating, and accepts", async () => {
    let n = 0
    const calls = mock({
      "/api/plan/preview-redraw": () => json(cand(["Alpha", "Beta"][n++])),
      "/api/plan/accept-redraw": () => json({ ok: true }),
    })
    const onDone = vi.fn()
    render(<PlanRedraw day="2026-10-20" onDone={onDone} onCancel={() => {}} />)
    await userEvent.click(screen.getByRole("button", { name: "Find another workout" }))
    expect(await screen.findByText(/Alpha/)).toBeTruthy()
    await userEvent.click(screen.getByRole("button", { name: "Another" }))
    expect(await screen.findByText(/Beta/)).toBeTruthy()
    expect(calls[1].body).toEqual({ date: "2026-10-20", exclude_extra: ["Alpha"] })
    await userEvent.click(screen.getByRole("button", { name: "Use this" }))
    await waitFor(() => expect(onDone).toHaveBeenCalled())
    expect(calls[2].body).toMatchObject({ date: "2026-10-20", zwo_file: "Beta.zwo", zwo_name: "Beta" })
  })

  it("says so when nothing else fits", async () => {
    mock({ "/api/plan/preview-redraw": () => json({ ok: false, action: "no_candidate", day: "2026-10-20" }) })
    render(<PlanRedraw day="2026-10-20" onDone={() => {}} onCancel={() => {}} />)
    await userEvent.click(screen.getByRole("button", { name: "Find another workout" }))
    expect((await screen.findByRole("alert")).textContent).toContain("No other workout fits")
  })
})

describe("PlanRematch", () => {
  it("previews the changes, then saves them", async () => {
    const calls = mock({
      "/api/plan/rematch?apply=0": () => json({ ok: true, matches: [
        { session_date: "2026-10-14", session_type: "z2", current_status: "pending", new_status: "done" },
        { session_date: "2026-10-15", session_type: "tempo", current_status: "missed", new_status: "missed" },
      ] }),
      "/api/plan/rematch?apply=1": () => json({ ok: true, changed: 1 }),
    })
    const onDone = vi.fn()
    render(<PlanRematch onDone={onDone} onCancel={() => {}} />)
    await userEvent.click(screen.getByRole("button", { name: "Check this week against my rides" }))
    expect(await screen.findByText("2026-10-14 z2: done")).toBeTruthy()
    expect(screen.queryByText(/tempo/)).toBeNull()
    expect(calls).toHaveLength(1)
    await userEvent.click(screen.getByRole("button", { name: "Save these matches" }))
    await waitFor(() => expect(onDone).toHaveBeenCalled())
    expect(calls[1].url).toBe("/api/plan/rematch?apply=1")
  })
})

describe("Plan tools in the screen", () => {
  const session = (day: string, over = {}) => ({ day, day_name: "", session_type: "z2", duration_min: 60, tss_estimate: 50, description: "", zwo_name: "", status: "pending", ...over })
  const planWith = (extra = {}, sessions = [session(addDays(1), { session_type: "ftp_test", zwo_name: "Test" })]) => ({
    plan_json: { goal: {}, phases: [], weeks: [{ week_num: 1, start: addDays(-1), end: addDays(5), phase: "base", tss_target: 300, is_stepback: false, sessions }], ...extra },
  })

  it("sets the FTP-test type on a test session", async () => {
    const calls = mock({ "/api/plan": () => json(planWith()), "/api/plan/ftp-test-type": () => json({ ok: true }) })
    render(<Plan />)
    await userEvent.selectOptions(await screen.findByLabelText(/^Test type /), "ramp")
    await waitFor(() => expect(calls.some((c) => c.url === "/api/plan/ftp-test-type")).toBe(true))
    expect(calls.find((c) => c.url === "/api/plan/ftp-test-type")!.body).toEqual({ date: addDays(1), test_type: "ramp" })
  })

  it("offers to undo a deload only while one is active, and says when nothing was undone", async () => {
    mock({ "/api/plan": () => json(planWith({ deload_advance: { week_num: 1 } })), "/api/plan/continuous/deload-revert": () => json({ reverted: false, reason: "week_passed" }) })
    render(<Plan />)
    await userEvent.click(await screen.findByRole("button", { name: "Undo the deload" }))
    expect((await screen.findByRole("alert")).textContent).toContain("week passed")
  })

  it("hides the undo button when there is no deload or it was already reverted", async () => {
    mock({ "/api/plan": () => json(planWith({ deload_advance: { week_num: 1, reverted: true } })) })
    render(<Plan />)
    await screen.findByText(/Week 1/)
    expect(screen.queryByRole("button", { name: "Undo the deload" })).toBeNull()
  })

  it("opens each tool from the row of buttons", async () => {
    mock({ "/api/plan": () => json(planWith()) })
    render(<Plan />)
    await userEvent.click(await screen.findByRole("button", { name: "Add a race…" }))
    expect(screen.getByLabelText("Race date")).toBeTruthy()
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }))
    await userEvent.click(screen.getByRole("button", { name: "Match rides…" }))
    expect(screen.getByRole("button", { name: "Check this week against my rides" })).toBeTruthy()
  })

  it("links to the races and injury screens", async () => {
    mock({ "/api/plan": () => json(planWith()) })
    render(<Plan />)
    expect((await screen.findByRole("link", { name: "All races" })).getAttribute("href")).toBe("#/races")
    expect(screen.getByRole("link", { name: "Injury and illness" }).getAttribute("href")).toBe("#/injury")
  })
})


describe("PlanRace import from intervals.icu", () => {
  it("lists upcoming races and adds the one chosen", async () => {
    const calls = mock({
      "/api/icu/races": () => json({ races: [{ date: addDays(30), name: "Club crit", priority: "C" }] }),
      "/api/plan/add-race": () => json({ ok: true }),
    })
    const onDone = vi.fn()
    render(<PlanRace onDone={onDone} onCancel={() => {}} />)
    await userEvent.click(screen.getByRole("button", { name: "Import from intervals.icu" }))
    await userEvent.click(await screen.findByRole("button", { name: `Add Club crit on ${addDays(30)}` }))
    await waitFor(() => expect(onDone).toHaveBeenCalled())
    expect(calls.find((c) => c.url === "/api/plan/add-race")!.body).toEqual({ date: addDays(30), name: "Club crit", priority: "C" })
  })

  it("says to reconnect, or that there are none", async () => {
    let reply: unknown = { needs_reconnect: true }
    mock({ "/api/icu/races": () => json(reply) })
    render(<PlanRace onDone={() => {}} onCancel={() => {}} />)
    await userEvent.click(screen.getByRole("button", { name: "Import from intervals.icu" }))
    expect((await screen.findByRole("status")).textContent).toContain("Reconnect intervals.icu")
    reply = { races: [] }
    await userEvent.click(screen.getByRole("button", { name: "Import from intervals.icu" }))
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("No upcoming races"))
  })
})
