import { cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { Library } from "@/screens/Library"
import { Shuffle } from "@/screens/Shuffle"

const row = (n: number, over = {}) => ({
  Name: `Workout ${n}`, Category: "Workout", File: `w${n}.zwo`, "Duration(min)": 60 + n, TSS: 70, IF: 0.85, Tags: [], display_name: `Sweet Spot ${n}`, ...over,
})
const DETAIL = { name: "W", description: "Steady: 10min @ 90% FTP", total_seconds: 600, ftp: 200, hr_available: false, segments: [{ type: "SteadyState", start: 0, duration: 600, power: 180, pct: 90 }] }
const json = (b: unknown, status = 200, headers: Record<string, string> = {}) => new Response(JSON.stringify(b), { status, headers })

function mock(handler: (url: string) => Response) {
  const urls: string[] = []
  vi.stubGlobal("fetch", vi.fn(async (url: string) => { urls.push(url); return handler(url) }))
  return urls
}
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers() })

describe("Library", () => {
  it("lists workouts with the library size, and opens one to its profile and download", async () => {
    mock((u) => (u.startsWith("/api/workouts?") ? json([row(1), row(2)], 200, { "X-Library-Total": "4200" }) : json(DETAIL)))
    render(<Library />)
    expect(await screen.findByText("Sweet Spot 1")).toBeTruthy()
    expect(screen.getByText(/Showing 2 of 4200/)).toBeTruthy()
    await userEvent.click(screen.getByRole("button", { name: "Sweet Spot 1" }))
    expect(await screen.findByRole("img", { name: /Power profile, 10 min, peak 120% of FTP/ })).toBeTruthy()
    expect(screen.getByText("Steady: 10min @ 90% FTP")).toBeTruthy()
    expect((screen.getByRole("link", { name: "Download .zwo" }) as HTMLAnchorElement).getAttribute("href")).toBe("/api/workout/download/w1.zwo")
  })

  it("filters by type and tag, narrows to gravel-suitable workouts, and clears", async () => {
    const urls = mock((u) =>
      u.startsWith("/api/workouts/tags") ? json({ tags: ["ftp_test", "outdoor"] })
      : json([row(1, { Protocol: "VO2max", Name: "Intervals" }), row(2, { Protocol: "Sweet Spot", Name: "Steady" })]))
    render(<Library />)
    await screen.findByText("Sweet Spot 1")
    await userEvent.selectOptions(screen.getByLabelText("Type"), "threshold")
    await userEvent.click(await screen.findByRole("button", { name: "outdoor" }))
    await waitFor(() => {
      expect(urls.at(-1)).toContain("content_class=threshold")
      expect(urls.at(-1)).toContain("tags=outdoor")
    })
    await userEvent.click(screen.getByRole("checkbox", { name: "Suits gravel and cobbles" }))
    await waitFor(() => expect(screen.queryByText("Sweet Spot 1")).toBeNull())
    expect(screen.getByText("Sweet Spot 2")).toBeTruthy()
    await userEvent.click(screen.getByRole("button", { name: "Clear filters" }))
    await waitFor(() => expect(urls.at(-1)).not.toContain("content_class"))
    expect(await screen.findByText("Sweet Spot 1")).toBeTruthy()
  })

  it("adds the outdoor variant to the .zwo download and offers a .fit file", async () => {
    mock((u) => (u.startsWith("/api/workouts?") ? json([row(1)]) : u.startsWith("/api/workout/") ? json(DETAIL) : json({}, 404)))
    render(<Library />)
    await userEvent.click(await screen.findByRole("checkbox", { name: "Outdoor variant for downloads" }))
    await userEvent.clear(screen.getByLabelText("Spin home (min)"))
    await userEvent.type(screen.getByLabelText("Spin home (min)"), "30")
    await userEvent.click(screen.getByRole("button", { name: "Sweet Spot 1" }))
    expect((await screen.findByRole("link", { name: "Download .zwo" })).getAttribute("href")).toBe("/api/download/zwo/w1.zwo?outdoor=1&transit_min=10&spin_min=30")
    expect(screen.getByRole("link", { name: "Download .fit" }).getAttribute("href")).toContain("/api/export/fit-workout?zwo_file=w1.zwo")
  })

  it("asks the server after a pause in typing, with the filters", async () => {
    const urls = mock(() => json([row(1)]))
    render(<Library />)
    await screen.findByText("Sweet Spot 1")
    await userEvent.type(screen.getByLabelText("Search"), "3x16")
    await userEvent.type(screen.getByLabelText("From (min)"), "45")
    await waitFor(() => expect(urls.at(-1)).toContain("search=3x16"))
    expect(urls.at(-1)).toContain("duration_min=45")
    expect(urls.at(-1)).toContain("sort=score_desc")
  })

  it("says so when nothing matches, and when the load fails, with a retry", async () => {
    let fail = true
    mock(() => (fail ? json({ error: "boom" }, 500) : json([])))
    render(<Library />)
    expect((await screen.findByRole("alert")).textContent).toContain("boom")
    fail = false
    await userEvent.click(screen.getByRole("button", { name: "Retry" }))
    expect(await screen.findByText("No workouts match.")).toBeTruthy()
  })

  it("flags a duration range that runs backwards", async () => {
    mock(() => json([]))
    render(<Library />)
    await userEvent.type(screen.getByLabelText("From (min)"), "90")
    await userEvent.type(screen.getByLabelText("To (min)"), "30")
    expect(screen.getByText(/“From” is longer than “To”/)).toBeTruthy()
  })

  it("tells the rider when the page is full", async () => {
    mock(() => json(Array.from({ length: 60 }, (_, i) => row(i)), 200, { "X-Library-Total": "900" }))
    render(<Library />)
    expect(await screen.findByText(/Narrow the search/)).toBeTruthy()
  })
})

describe("Shuffle", () => {
  it("sends how you feel and the time you have, and lists the suggestions", async () => {
    const urls = mock((u) => (u.startsWith("/api/picker") ? json({ type: "z2", readiness: 71.2, advice: "Keep it steady.", baseline_used: true, workouts: [row(1)] }) : json(DETAIL)))
    render(<Shuffle />)
    await userEvent.clear(screen.getByLabelText("Time available (min)"))
    await userEvent.type(screen.getByLabelText("Time available (min)"), "90")
    await userEvent.click(screen.getByRole("button", { name: "Suggest workouts" }))
    expect(await screen.findByText("Sweet Spot 1")).toBeTruthy()
    expect(urls[0]).toBe("/api/picker?subjective=7&duration=90")
    expect(screen.getByText(/Readiness 71\/100/)).toBeTruthy()
    expect(screen.getByText(/neutral baseline/)).toBeTruthy()
    expect(screen.getByRole("button", { name: "Shuffle again" })).toBeTruthy()
  })

  it("refuses a time outside 20 to 300 minutes", async () => {
    mock(() => json({}))
    render(<Shuffle />)
    await userEvent.clear(screen.getByLabelText("Time available (min)"))
    await userEvent.type(screen.getByLabelText("Time available (min)"), "5")
    expect((screen.getByRole("button", { name: "Suggest workouts" }) as HTMLButtonElement).disabled).toBe(true)
  })

  it("shows the failure with a retry", async () => {
    mock(() => json({ detail: "no" }, 500))
    render(<Shuffle />)
    await userEvent.click(screen.getByRole("button", { name: "Suggest workouts" }))
    expect((await screen.findByRole("alert")).textContent).toContain("no")
  })
})
