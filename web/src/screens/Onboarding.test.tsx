import { cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { readProgress } from "@/lib/onboarding"
import { Onboarding } from "@/screens/Onboarding"

type Call = { url: string; method: string; body?: Record<string, unknown> }
const SETTINGS = { weight: 70, ftp: 250, lthr: 170, max_hr: 190, target_mode: "power", lthr_is_set: false, power_zones: [], hr_zones: [] }

function mockApi(state: { connected: boolean; lthrSet: boolean; llm: boolean; weeks: number }) {
  const calls: Call[] = []
  const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, method: init?.method ?? "GET", body: init?.body ? JSON.parse(String(init.body)) : undefined })
    if (url === "/api/icu/connection") return json({ connected: state.connected, name: "Sam", oauth_available: false })
    if (url === "/api/settings" && init?.method === "POST") { state.lthrSet = true; return json({ settings: { ...SETTINGS, lthr_is_set: true } }) }
    if (url === "/api/settings") return json({ ...SETTINGS, lthr_is_set: state.lthrSet })
    if (url === "/api/setup/limits") return json({ ftp: [50, 600], weight: [30, 200], lthr: [100, 220], max_hr: [140, 220] })
    if (url === "/api/llm") return json({ configured: state.llm, has_key: false, provider: "", model: "", base_url: "" })
    if (url === "/api/folders" || url.startsWith("/api/workout-folders")) return json({ builtin: { count: 100 }, extra: null })
    if (url === "/api/plan") return json({ plan_json: { goal: {}, phases: [], weeks: Array.from({ length: state.weeks }, (_, i) => ({ week_num: i, start: "2026-01-01", end: "2026-01-07", sessions: [] })) } })
    if (url === "/api/projection" || url.includes("projection")) return json({ available: false })
    return json({}, 404)
  }))
  return calls
}

afterEach(() => { cleanup(); vi.unstubAllGlobals(); localStorage.clear() })

const saved = () => readProgress("shepherd_onboarding:")

describe("Onboarding", () => {
  it("starts at the first step with its reason, and blocks Continue until intervals.icu is connected", async () => {
    mockApi({ connected: false, lthrSet: false, llm: false, weeks: 0 })
    render(<Onboarding />)
    expect(await screen.findByRole("heading", { name: "Connect intervals.icu" })).toBeTruthy()
    expect(screen.getByText(/where your rides, sleep and heart-rate data come from/)).toBeTruthy()
    await userEvent.click(screen.getByRole("button", { name: "Continue" }))
    expect((await screen.findByRole("alert")).textContent).toMatch(/not connected yet/)
    expect(saved().done).toEqual([])
  })

  it("moves on once the check passes and remembers it", async () => {
    mockApi({ connected: true, lthrSet: false, llm: false, weeks: 0 })
    render(<Onboarding />)
    expect(await screen.findByText(/Connected as Sam/)).toBeTruthy()
    await userEvent.click(screen.getByRole("button", { name: "Continue" }))
    expect(await screen.findByRole("heading", { name: "Your rider numbers" })).toBeTruthy()
    expect(saved().done).toEqual(["icu"])
  })

  it("saves the rider numbers, then lets the rider continue", async () => {
    const calls = mockApi({ connected: true, lthrSet: false, llm: false, weeks: 0 })
    localStorage.setItem("shepherd_onboarding:", JSON.stringify({ done: ["icu"], skipped: [], finished: false }))
    render(<Onboarding />)
    expect(await screen.findByRole("heading", { name: "Your rider numbers" })).toBeTruthy()
    await userEvent.click(screen.getByRole("button", { name: "Continue" }))
    expect((await screen.findByRole("alert")).textContent).toMatch(/Save your rider numbers/)
    await userEvent.click(screen.getByRole("button", { name: "Save rider numbers" }))
    await screen.findByText("Saved.")
    expect(calls.find((c) => c.url === "/api/settings" && c.method === "POST")?.body).toEqual({ weight: 70, ftp: 250, lthr: 170, max_hr: 190, target_mode: "power" })
    await userEvent.click(screen.getByRole("button", { name: "Continue" }))
    expect(await screen.findByRole("heading", { name: "AI coach (optional)" })).toBeTruthy()
  })

  it("rejects an out-of-range number before saving", async () => {
    mockApi({ connected: true, lthrSet: false, llm: false, weeks: 0 })
    localStorage.setItem("shepherd_onboarding:", JSON.stringify({ done: ["icu"], skipped: [], finished: false }))
    render(<Onboarding />)
    const ftp = await screen.findByLabelText("FTP (W)")
    await userEvent.clear(ftp)
    await userEvent.type(ftp, "9000")
    expect(await screen.findByText("FTP must be between 50 and 600.")).toBeTruthy()
    expect((screen.getByRole("button", { name: "Save rider numbers" }) as HTMLButtonElement).disabled).toBe(true)
  })

  it("can skip a step, and shows it as skipped in the list", async () => {
    mockApi({ connected: false, lthrSet: false, llm: false, weeks: 0 })
    render(<Onboarding />)
    await screen.findByRole("heading", { name: "Connect intervals.icu" })
    await userEvent.click(screen.getByRole("button", { name: "Skip for now" }))
    expect(await screen.findByRole("heading", { name: "Your rider numbers" })).toBeTruthy()
    expect(saved().skipped).toEqual(["icu"])
    expect(screen.getByRole("button", { name: /1\. Connect intervals\.icu\s*Skipped/ })).toBeTruthy()
  })

  it("finishing the tour marks the whole setup finished", async () => {
    mockApi({ connected: true, lthrSet: true, llm: false, weeks: 4 })
    localStorage.setItem("shepherd_onboarding:", JSON.stringify({ done: ["icu", "rider", "goal"], skipped: ["ai", "folders"], finished: false }))
    render(<Onboarding />)
    expect(await screen.findByRole("heading", { name: "A short tour" })).toBeTruthy()
    for (const name of ["Home", "Training Plan", "Workout Library", "Analysis", "Settings"]) expect(screen.getAllByRole("link", { name })[0]).toBeTruthy()
    await userEvent.click(screen.getByRole("button", { name: "Finish" }))
    await waitFor(() => expect(saved().finished).toBe(true))
    expect(await screen.findByText(/You have been through every step/)).toBeTruthy()
  })
})
