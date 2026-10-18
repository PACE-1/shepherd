import { cleanup, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { bodyOf, emptyForm, formProblem, progress } from "@/lib/gear"
import { Gear } from "@/screens/Gear"

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })
const item = (over: Record<string, unknown> = {}) => ({
  id: "b1", name: "Road", kind: "bike", parent_id: null, retired: false, started_on: null, icu_name: null,
  service_every_km: 1000, service_every_hours: null, km: 940, hours: 30, km_pct: 0.94, hours_pct: null,
  state: "due_soon", last_service: null, services: [], ...over,
})
const overview = (over: Record<string, unknown> = {}) => ({
  items: [item()], suggestions: [], method: "Distance and hours add up.",
  recent: [{ id: "act1", date: "2026-10-12", name: "Morning ride", sport: "Ride", distance_km: 50, gear_id: null, source: "none" }],
  ...over,
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe("gear lib", () => {
  it("never invents a threshold and rejects a bad one", () => {
    expect(bodyOf({ ...emptyForm(), name: " Shoes ", kind: "shoes" })).toMatchObject({ name: "Shoes", service_every_km: null, service_every_hours: null, parent_id: null })
    expect(formProblem(emptyForm())).toMatch(/name/)
    expect(formProblem({ ...emptyForm(), name: "x", service_every_km: "0" })).toMatch(/above 0/)
    expect(formProblem({ ...emptyForm(), name: "x", service_every_km: "800" })).toBe("")
  })
  it("shows progress against the threshold only when there is one", () => {
    expect(progress(412.34, 1000, "km", 0.412)).toBe("412.3 / 1000 km (41%)")
    expect(progress(412, null, "km", null)).toBe("412 km")
  })
})

describe("Gear", () => {
  it("shows what is due, marks service done, adds gear from an intervals.icu name and assigns a ride", async () => {
    let current = overview({ suggestions: [{ icu_name: "Canyon", rides: 3 }] })
    const calls: { url: string; method: string; body: unknown }[] = []
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const method = init?.method ?? "GET"
        calls.push({ url, method, body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined })
        if (method === "POST" && url === "/api/gear/b1/service") current = overview({ items: [item({ km: 0, km_pct: 0, state: "ok", last_service: "2026-10-18" })] })
        if (method === "POST" && url === "/api/gear") current = overview({ items: [item(), item({ id: "b2", name: "Canyon", icu_name: "Canyon", km: 150, state: "ok", service_every_km: null, km_pct: null })] })
        if (method === "PUT") current = overview({ recent: [{ ...current.recent[0], gear_id: "b1", source: "manual" }] })
        return json(current)
      }),
    )
    const user = userEvent.setup()
    render(<Gear />)
    expect((await screen.findByRole("status")).textContent).toContain("Road: service is due soon, 940 / 1000 km (94%).")
    expect(screen.getByRole("status").textContent).toContain("not send them as notifications")

    await user.click(screen.getByRole("button", { name: "Use Canyon (3 rides)" }))
    await user.click(screen.getByRole("button", { name: "Add gear" }))
    await waitFor(() => expect(calls.find((c) => c.method === "POST" && c.url === "/api/gear")?.body).toMatchObject({ name: "Canyon", icu_name: "Canyon", kind: "bike", service_every_km: null }))

    await user.selectOptions(await screen.findByLabelText("Gear for 2026-10-12 Morning ride"), "b1")
    await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ activity_id: "act1", gear_id: "b1" }))

    await user.click(screen.getByRole("button", { name: "Service done for Road" }))
    await waitFor(() => expect(calls.find((c) => c.url === "/api/gear/b1/service")).toBeTruthy())
    await waitFor(() => expect(screen.queryByRole("status")).toBeNull())
    expect(within(screen.getByRole("table", { name: "Gear" })).getByText("serviced 2026-10-18", { exact: false })).toBeTruthy()
  })

  it("says so when there is no gear yet and shows a load error with retry", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json(overview({ items: [], recent: [] }))))
    render(<Gear />)
    expect(await screen.findByText(/No gear yet/)).toBeTruthy()
    expect(screen.queryByRole("status")).toBeNull()
    cleanup()
    vi.stubGlobal("fetch", vi.fn(async () => json({ detail: "boom" }, 500)))
    render(<Gear />)
    expect((await screen.findAllByRole("alert")).length).toBeGreaterThan(0)
  })
})
