import { cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { NutritionSettings } from "@/screens/NutritionSettings"

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })
const NONE = { configured: false, base_url: "", has_key: false, last_synced_at: null }
const SAVED = { configured: true, base_url: "http://192.168.1.20:3004", has_key: true, last_synced_at: null }

function mock(routes: Record<string, (body: unknown, method?: string) => Response>) {
  const calls: { url: string; method?: string; body: unknown }[] = []
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const body = init?.body ? JSON.parse(init.body as string) : undefined
    calls.push({ url, method: init?.method, body })
    const r = routes[url]
    return r ? r(body, init?.method) : json({}, 404)
  }))
  return calls
}
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe("NutritionSettings", () => {
  it("saves the address and key, then clears the key field and never shows it", async () => {
    let state = NONE
    const calls = mock({ "/api/nutrition/connection": (b) => ((state = b ? SAVED : state), json(state)) })
    render(<NutritionSettings />)
    expect(await screen.findByText("SparkyFitness is not connected.")).toBeTruthy()
    await userEvent.type(screen.getByLabelText("SparkyFitness address"), "http://192.168.1.20:3004")
    const key = screen.getByLabelText("SparkyFitness API key") as HTMLInputElement
    expect(key.type).toBe("password")
    await userEvent.type(key, "secret-key")
    await userEvent.click(screen.getByRole("button", { name: "Save" }))
    expect(await screen.findByText("Connected to http://192.168.1.20:3004.")).toBeTruthy()
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ base_url: "http://192.168.1.20:3004", api_key: "secret-key" })
    expect((screen.getByLabelText("SparkyFitness API key") as HTMLInputElement).value).toBe("")
    expect(screen.getByLabelText("SparkyFitness API key").getAttribute("placeholder")).toMatch(/Saved/)
  })

  it("tests the connection, syncs, and shows a server error", async () => {
    mock({
      "/api/nutrition/connection": () => json(SAVED),
      "/api/nutrition/test": () => json({ ok: true, message: "Connected: SparkyFitness accepted the key." }),
      "/api/nutrition/sync": () => json({ start: "2026-09-19", end: "2026-10-18", days_with_data: 12, synced_at: "2026-10-18T09:00:00" }),
    })
    render(<NutritionSettings />)
    await userEvent.click(await screen.findByRole("button", { name: "Test connection" }))
    expect(await screen.findByText("Connected: SparkyFitness accepted the key.")).toBeTruthy()
    await userEvent.click(screen.getByRole("button", { name: "Sync nutrition now" }))
    expect(await screen.findByText("Synced 2026-09-19 to 2026-10-18: 12 days with entries.")).toBeTruthy()
  })

  it("shows why the test failed", async () => {
    mock({
      "/api/nutrition/connection": () => json(SAVED),
      "/api/nutrition/test": () => json({ detail: "SparkyFitness rejected the API key (wrong or expired)." }, 502),
    })
    render(<NutritionSettings />)
    await userEvent.click(await screen.findByRole("button", { name: "Test connection" }))
    await waitFor(() => expect(screen.getByRole("alert").textContent).toMatch(/rejected the API key/))
  })
})
