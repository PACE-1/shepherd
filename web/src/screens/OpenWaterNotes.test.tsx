import { cleanup, render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { OpenWaterNotes } from "@/screens/OpenWaterNotes"

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

type Note = Record<string, unknown> & { id: string; date: string }

function server(initial: Note[] = []) {
  let notes = [...initial]
  const calls: { url: string; method: string; body?: unknown }[] = []
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET"
    const body = init?.body ? JSON.parse(init.body as string) : undefined
    calls.push({ url, method, body })
    if (url === "/api/swim/open-water" && method === "GET") return json({ notes })
    if (url === "/api/swim/open-water" && method === "POST") {
      const n = { id: `n${notes.length + 1}`, ...body }
      notes = [n, ...notes]
      return json(n)
    }
    const m = /^\/api\/swim\/open-water\/(.+)$/.exec(url)
    if (m && method === "PUT") {
      notes = notes.map((n) => (n.id === m[1] ? { ...n, ...body } : n))
      return json(notes.find((n) => n.id === m[1]))
    }
    if (m && method === "DELETE") {
      notes = notes.filter((n) => n.id !== m[1])
      return json({ ok: true })
    }
    return json({}, 404)
  }))
  return calls
}

describe("OpenWaterNotes", () => {
  it("adds a note linked to a swim, then edits and deletes it", async () => {
    const calls = server()
    render(<OpenWaterNotes swims={[{ id: "i9", date: "2026-07-01", name: "Lake swim" }]} />)
    expect(await screen.findByText("No open-water notes yet.")).toBeTruthy()
    await userEvent.click(screen.getByRole("button", { name: "Add a note" }))
    await userEvent.selectOptions(screen.getByLabelText("Swim (optional)"), "i9")
    await userEvent.type(screen.getByLabelText("Water temperature (°C)"), "16.5")
    await userEvent.selectOptions(screen.getByLabelText("Wetsuit"), "yes")
    await userEvent.type(screen.getByLabelText("Conditions"), "choppy")
    await userEvent.type(screen.getByLabelText("Sighting and navigation"), "drifted left")
    await userEvent.click(screen.getByRole("button", { name: "Save note" }))
    const list = await screen.findByRole("list", { name: "Open-water notes" })
    expect(within(list).getByText(/2026-07-01 · Lake swim · 16.5 °C · wetsuit · choppy/)).toBeTruthy()
    expect(within(list).getByText("Sighting: drifted left")).toBeTruthy()
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({
      date: "2026-07-01", activity_id: "i9", water_temp_c: 16.5, wetsuit: true, conditions: "choppy", course: "", sighting: "drifted left", note: "",
    })
    await userEvent.click(screen.getByRole("button", { name: "Edit note of 2026-07-01" }))
    await userEvent.selectOptions(screen.getByLabelText("Wetsuit"), "no")
    await userEvent.click(screen.getByRole("button", { name: "Save note" }))
    expect(await screen.findByText(/16.5 °C · no wetsuit · choppy/)).toBeTruthy()
    expect(calls.find((c) => c.method === "PUT")?.url).toBe("/api/swim/open-water/n1")
    await userEvent.click(screen.getByRole("button", { name: "Delete note of 2026-07-01" }))
    expect(await screen.findByText("No open-water notes yet.")).toBeTruthy()
  })

  it("refuses a temperature that is not a number without calling the server", async () => {
    const calls = server()
    render(<OpenWaterNotes />)
    await userEvent.click(await screen.findByRole("button", { name: "Add a note" }))
    expect(screen.queryByLabelText("Swim (optional)")).toBeNull()
    await userEvent.type(screen.getByLabelText("Water temperature (°C)"), "cold")
    await userEvent.click(screen.getByRole("button", { name: "Save note" }))
    expect((await screen.findByRole("alert")).textContent).toContain("water temperature")
    expect(calls.some((c) => c.method === "POST")).toBe(false)
  })
})
