import { cleanup, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { move, pushMessage, startingSteps, toWire } from "@/lib/builder"
import { Library } from "@/screens/Library"
import { WorkoutBuilder } from "@/screens/WorkoutBuilder"

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })
const OK = {
  ok: true, errors: [], warnings: [], duration_s: 1860, intensity_factor: 0.81, tss: 33.5,
  profile: [{ x: 0, y: 50 }, { x: 10, y: 70 }, { x: 10, y: 105 }, { x: 14, y: 105 }],
}
// Request bodies are whatever the screen sent; the tests read the fields they care about.
type Body = { date?: string; file?: string; workout: { name: string; steps: { kind: string; duration_s: number; target: unknown }[] } }
type Call = { url: string; body: Body }

function mock(handler: (url: string, body: Body) => Response) {
  const calls: Call[] = []
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const body = typeof init?.body === "string" ? JSON.parse(init.body) : undefined
    calls.push({ url, body })
    return handler(url, body)
  }))
  return calls
}
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe("builder helpers", () => {
  it("moves a step and leaves the list alone at the ends", () => {
    expect(move([1, 2, 3], 0, 1)).toEqual([2, 1, 3])
    expect(move([1, 2, 3], 0, -1)).toEqual([1, 2, 3])
    expect(move([1, 2, 3], 2, 1)).toEqual([1, 2, 3])
  })
  it("sends steps without the screen's own ids", () => {
    const w = toWire("A", "", startingSteps())
    expect(JSON.stringify(w)).not.toContain("uid")
    expect(w.steps.map((s) => s.kind)).toEqual(["warmup", "repeat", "cooldown"])
  })
  it("says why a push did not go, never as success", () => {
    expect(pushMessage({ ok: true }, "2026-11-01")).toEqual({ ok: true, text: "Sent to your intervals.icu calendar for 2026-11-01." })
    expect(pushMessage({ needs_reconnect: true }, "d").text).toContain("permission to write")
    expect(pushMessage({ needs_lthr: true }, "d").text).toContain("threshold heart rate")
    expect(pushMessage({ error: "http_500" }, "d")).toMatchObject({ ok: false, text: expect.stringContaining("http 500") })
    expect(pushMessage({ error: "not_connected" }, "d").text).toContain("isn't connected")
  })
})

describe("WorkoutBuilder", () => {
  it("shows the live preview numbers and intensity chart for the starting workout", async () => {
    const calls = mock(() => json(OK))
    render(<WorkoutBuilder />)
    expect(await screen.findByText(/31:00 · IF 0.81 · TSS 33.5/)).toBeTruthy()
    expect(screen.getByRole("img", { name: "Intensity profile, 31:00 long" })).toBeTruthy()
    expect(calls[0].url).toBe("/api/builder/preview")
    expect(calls[0].body.workout.steps).toHaveLength(3)
  })

  it("adds, reorders and deletes steps, and the server sees the new order", async () => {
    const calls = mock(() => json(OK))
    render(<WorkoutBuilder />)
    await userEvent.click(screen.getByRole("button", { name: "Add recovery" }))
    expect(screen.getByRole("group", { name: "Step 4: Recovery" })).toBeTruthy()
    await userEvent.click(screen.getByRole("button", { name: "Move Step 4 up" }))
    expect(screen.getByRole("group", { name: "Step 3: Recovery" })).toBeTruthy()
    expect((screen.getByRole("button", { name: "Move Step 1 up" }) as HTMLButtonElement).disabled).toBe(true)
    await userEvent.click(screen.getByRole("button", { name: "Delete Step 1" }))
    await waitFor(() => expect(calls.at(-1)!.body.workout.steps.map((s) => s.kind)).toEqual(["repeat", "recovery", "cooldown"]))
  })

  it("edits a target through labelled fields and switches a step to heart rate", async () => {
    const calls = mock(() => json(OK))
    render(<WorkoutBuilder />)
    const step1 = screen.getByRole("group", { name: "Step 1: Warm-up" })
    await userEvent.clear(within(step1).getByLabelText("Step 1 minutes"))
    await userEvent.type(within(step1).getByLabelText("Step 1 minutes"), "15")
    await userEvent.selectOptions(within(step1).getByLabelText("Step 1 target type"), "hr")
    await waitFor(() => {
      const s = calls.at(-1)!.body.workout.steps[0]
      expect(s.duration_s).toBe(900)
      expect(s.target).toEqual({ kind: "hr", lo: 70, hi: 80 })
    })
    expect(within(step1).getByLabelText("Step 1 low (% LTHR)")).toBeTruthy()
  })

  it("shows a server problem next to its step and keeps Save off until it is fixed", async () => {
    mock(() => json({ ok: false, errors: [{ path: "steps[0].target", message: "Target must be between 10 and 300 % FTP." }], warnings: [], duration_s: 0, profile: [] }))
    render(<WorkoutBuilder />)
    const step1 = screen.getByRole("group", { name: "Step 1: Warm-up" })
    expect(await within(step1).findByText("Target must be between 10 and 300 % FTP.")).toBeTruthy()
    expect((screen.getByRole("button", { name: "Save to library" }) as HTMLButtonElement).disabled).toBe(true)
    expect((screen.getByRole("button", { name: "Send to calendar" }) as HTMLButtonElement).disabled).toBe(true)
  })

  it("saves, then sends for the chosen date, and reports a refused push without losing the save", async () => {
    const calls = mock((url) =>
      url === "/api/builder/save" ? json({ ok: true, file: "builder_x.zwo", created: true })
      : url === "/api/builder/send" ? json({ ok: true, file: "builder_x.zwo", created: false, push: { needs_reconnect: true } })
      : json(OK))
    render(<WorkoutBuilder />)
    await userEvent.type(screen.getByLabelText("Name"), "Over unders")
    await screen.findByText(/IF 0.81/)
    await userEvent.click(screen.getByRole("button", { name: "Save to library" }))
    expect(await screen.findByText("Saved as builder_x.zwo. It’s in your Workout Library.")).toBeTruthy()

    await userEvent.clear(screen.getByLabelText("Calendar date"))
    await userEvent.type(screen.getByLabelText("Calendar date"), "2031-02-03")
    await userEvent.click(screen.getByRole("button", { name: "Send to calendar" }))
    const alert = await screen.findByRole("alert")
    expect(alert.textContent).toContain("Saved as builder_x.zwo, but it wasn’t sent.")
    expect(alert.textContent).toContain("permission to write")
    const sent = calls.find((c) => c.url === "/api/builder/send")!
    expect(sent.body).toMatchObject({ date: "2031-02-03", file: "builder_x.zwo", workout: { name: "Over unders" } })
  })

  it("opens a saved workout for editing", async () => {
    const calls = mock((url) =>
      url.startsWith("/api/builder/workout")
        ? json({ ok: true, file: "builder_x.zwo", workout: { name: "Saved one", description: "d", steps: [{ kind: "work", duration_s: 600, cadence_note: "", target: { kind: "power", lo: 88, hi: 94 } }] } })
        : json(OK))
    render(<WorkoutBuilder file="builder_x.zwo" />)
    await waitFor(() => expect((screen.getByLabelText("Name") as HTMLInputElement).value).toBe("Saved one"))
    expect(screen.getByRole("group", { name: "Step 1: Work" })).toBeTruthy()
    expect(calls[0].url).toBe("/api/builder/workout?file=builder_x.zwo")
  })

  it("opens a copy that saves as a new file", async () => {
    const calls = mock((url) =>
      url.startsWith("/api/builder/workout")
        ? json({ ok: true, file: "builder_x.zwo", workout: { name: "Saved one", description: "d", steps: [{ kind: "work", duration_s: 600, cadence_note: "", target: { kind: "power", lo: 88, hi: 94 } }] } })
        : url === "/api/builder/save" ? json({ ok: true, file: "builder_saved-one-copy.zwo", created: true })
        : json(OK))
    render(<WorkoutBuilder file="builder_x.zwo" copy />)
    await waitFor(() => expect((screen.getByLabelText("Name") as HTMLInputElement).value).toBe("Saved one (copy)"))
    await waitFor(() => expect((screen.getByRole("button", { name: "Save to library" }) as HTMLButtonElement).disabled).toBe(false))
    await userEvent.click(screen.getByRole("button", { name: "Save to library" }))
    await waitFor(() => expect(calls.some((c) => c.url === "/api/builder/save")).toBe(true))
    expect(calls.find((c) => c.url === "/api/builder/save")!.body.file).toBeUndefined()
  })
})

describe("Library entry point", () => {
  it("offers a New workout link to the builder", async () => {
    mock(() => json([]))
    render(<Library />)
    expect(screen.getByRole("link", { name: "New workout" }).getAttribute("href")).toBe("#/builder")
  })

  it("offers Edit and Duplicate only on workouts the builder made", async () => {
    const row = (File: string) => ({ Category: "own", File, Name: File, display_name: File, "Duration(min)": 30, TSS: 30, IF: 0.8, content_class: "endurance" })
    mock((url) => url.startsWith("/api/workout/") ? json({ total_seconds: 60, segments: [], description: "d" })
      : json(url.startsWith("/api/workouts?") ? [row("builder_x.zwo"), row("other.zwo")] : []))
    render(<Library />)
    for (const b of await screen.findAllByRole("button", { name: /\.zwo/ })) await userEvent.click(b)
    expect(screen.getAllByRole("link", { name: "Edit" })).toHaveLength(1)
    expect(screen.getByRole("link", { name: "Edit" }).getAttribute("href")).toBe("#/builder/builder_x.zwo")
    expect(screen.getByRole("link", { name: "Duplicate" }).getAttribute("href")).toBe("#/builder/copy/builder_x.zwo")
  })
})
