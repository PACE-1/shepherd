import { cleanup, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { Garmin } from "@/screens/Garmin"

const BASE = { available: true, connected: false, needs_login: false, mfa_pending: false, name: "", relay_to_icu: false, last_sync_at: null, last_error: null, health_days: 0, activities_imported: 0 }
const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })

function mock(routes: Record<string, (body: unknown) => Response>) {
  const calls: { url: string; method?: string; body: unknown }[] = []
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const body = init?.body ? JSON.parse(init.body as string) : undefined
    calls.push({ url, method: init?.method, body })
    const r = routes[`${init?.method ?? "GET"} ${url}`]
    return r ? r(body) : json({}, 404)
  }))
  return calls
}
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe("Garmin", () => {
  it("signs in, asks for the MFA code and verifies it", async () => {
    let state = { ...BASE }
    const calls = mock({
      "GET /api/garmin": () => json(state),
      "POST /api/garmin/login": () => ((state = { ...BASE, mfa_pending: true }), json(state)),
      "POST /api/garmin/mfa": () => ((state = { ...BASE, connected: true, name: "Rider" }), json(state)),
    })
    render(<Garmin />)
    await userEvent.type(await screen.findByLabelText("Email"), "me@example.com")
    await userEvent.type(screen.getByLabelText("Password"), "pw")
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }))
    expect(await screen.findByText(/Garmin sent you a code/)).toBeTruthy()
    await userEvent.type(await screen.findByLabelText("Code from Garmin"), "123456")
    await userEvent.click(screen.getByRole("button", { name: "Verify" }))
    expect(await screen.findByText("Connected as Rider.")).toBeTruthy()
    expect(calls.find((c) => c.url === "/api/garmin/login")?.body).toEqual({ email: "me@example.com", password: "pw" })
    expect(calls.find((c) => c.url === "/api/garmin/mfa")?.body).toEqual({ code: "123456" })
  })

  it("syncs when connected and shows a rejected sign-in", async () => {
    mock({
      "GET /api/garmin": () => json({ ...BASE, connected: true, name: "Rider", last_sync_at: "2026-10-18T08:00:00Z", health_days: 3, activities_imported: 12 }),
      "POST /api/garmin/sync": () => json({ health_days: 3, activities_imported: 1 }),
    })
    render(<Garmin />)
    expect(await screen.findByText(/12 activities imported so far/)).toBeTruthy()
    await userEvent.click(screen.getByRole("button", { name: "Sync Garmin now" }))
    expect(await screen.findByText("Synced 3 days of health data and 1 new activities.")).toBeTruthy()
  })

  it("asks for a new sign-in when Garmin rejects the saved one", async () => {
    mock({ "GET /api/garmin": () => json({ ...BASE, connected: true, needs_login: true }) })
    render(<Garmin />)
    expect(await screen.findByText(/no longer accepts the saved sign-in/)).toBeTruthy()
    expect(screen.getByRole("button", { name: "Sign in" })).toBeTruthy()
  })
})
