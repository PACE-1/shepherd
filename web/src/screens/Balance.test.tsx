import { cleanup, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { SportBalance } from "@/screens/Balance"

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })
const Z = { cycling: 0, running: 0, swimming: 0, other: 0 }
const bucket = (start: string, hours: Partial<typeof Z>, gap: typeof Z | null = null) => {
  const h = { ...Z, ...hours }
  const total = h.cycling + h.running + h.swimming + h.other
  const share = Object.fromEntries(Object.entries(h).map(([k, v]) => [k, total ? Math.round((1000 * v) / total) / 10 : null]))
  return { key: start, label: `Week of ${start}`, start, end: start, hours: h, load: { ...h }, total_hours: total, total_load: total, hours_share: share, load_share: share, gap_pp: gap }
}
const base = { as_of: "2026-10-18", limiter_note: "Planner emphasis toward your limiter is not built yet; for now the sport is only highlighted.", method: "Hours come from duration.", targets: null, has_targets: false, limiter: null }
const MIXED = {
  ...base, has_history: true, sports_present: ["cycling", "running"], single_sport: null,
  weeks: [bucket("2026-10-05", { cycling: 6, running: 2 }), bucket("2026-10-12", { cycling: 3, running: 1 }, { cycling: 25, running: -5, swimming: -20, other: 0 })],
  months: [bucket("2026-10-01", { cycling: 9, running: 3 }, { cycling: 25, running: -5, swimming: -20, other: 0 })],
}
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe("SportBalance", () => {
  it("shows a chart with a text alternative, this week and month against the target, and the limiter", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json({ ...MIXED, has_targets: true, targets: { cycling: 50, running: 30, swimming: 20, other: 0 }, limiter: "swimming" })))
    render(<SportBalance />)
    const chart = await screen.findByRole("img")
    expect(chart.getAttribute("aria-label")).toContain("2 weeks from 2026-10-05")
    const table = screen.getByRole("table")
    expect(table.textContent).toContain("Swimming (limiter)")
    expect(table.textContent).toContain("+25 pp")
    expect(table.textContent).toContain("-20 pp")
    expect(screen.getByText(/not built yet/)).toBeTruthy()
  })

  it("is a plain all-cycling view for a cycling-only rider", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json({ ...base, has_history: true, sports_present: ["cycling"], single_sport: "cycling",
      weeks: [bucket("2026-10-12", { cycling: 5.5 })], months: [bucket("2026-10-01", { cycling: 20 })] })))
    render(<SportBalance />)
    expect((await screen.findByText(/All cycling: 5.5 h this week so far, 20 h this month/))).toBeTruthy()
    expect(screen.queryByText(/Set a target split below/)).toBeNull()
    expect(screen.queryByRole("alert")).toBeNull()
  })

  it("explains an empty history without an error", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json({ ...base, has_history: false, sports_present: [], single_sport: null, weeks: [bucket("2026-10-12", {})], months: [bucket("2026-10-01", {})] })))
    render(<SportBalance />)
    expect(await screen.findByText(/No activities in the last 1 weeks yet/)).toBeTruthy()
    expect(screen.queryByRole("img")).toBeNull()
    expect(screen.queryByRole("table")).toBeNull()
  })

  it("saves a target split and the limiter, and refuses a split that is not 100", async () => {
    const puts: unknown[] = []
    vi.stubGlobal("fetch", vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === "PUT") { puts.push(JSON.parse(String(init.body))); return json({ targets: null, has_targets: false, limiter: "running", limiter_note: "" }) }
      return json(MIXED)
    }))
    render(<SportBalance />)
    await userEvent.type(await screen.findByLabelText("Cycling target (%)"), "70")
    await userEvent.type(screen.getByLabelText("Running target (%)"), "20")
    await userEvent.click(screen.getByRole("button", { name: "Save targets" }))
    expect((await screen.findByRole("alert")).textContent).toContain("add up to 90")
    expect(puts).toEqual([])
    await userEvent.clear(screen.getByLabelText("Running target (%)"))
    await userEvent.type(screen.getByLabelText("Running target (%)"), "30")
    await userEvent.selectOptions(screen.getByLabelText("Your limiter (optional)"), "running")
    await userEvent.click(screen.getByRole("button", { name: "Save targets" }))
    expect((await screen.findByRole("status")).textContent).toBe("Saved.")
    expect(puts).toEqual([{ targets: { cycling: 70, running: 30, swimming: 0, other: 0 }, limiter: "running" }])
  })
})
