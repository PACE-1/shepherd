import { cleanup, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { carbStatus, range } from "@/lib/nutrition"
import { Fueling } from "@/screens/Fueling"

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })
const BASE = {
  date: "2026-10-18",
  weight_kg: 70,
  session: { session_type: "long_z2", duration_min: 180 },
  during: { band: "high", low_g_per_h: 60, high_g_per_h: 90, low_g: 180, high_g: 270, note: "Up to 90 g per hour, from a glucose plus fructose mix." },
  day: { load: "high", low_g_per_kg: 6, high_g_per_kg: 10, low_g: 420, high_g: 700 },
  logged: { date: "2026-10-18", source: "sparkyfitness", kcal: 900, carbs_g: 120, protein_g: 40, fat_g: 25, water_ml: 500, synced_at: "2026-10-18T09:00:00" },
  connected: true,
  ride_kcal_approx: null,
  hourly_method: "Jeukendrup 2014; ACSM/AND/DC 2016.",
  daily_method: "ACSM/AND/DC 2016.",
  energy_method: "Approximate.",
  note: "Not medical advice.",
}
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe("carbStatus", () => {
  it("says how far the day's logged carbohydrate is from the range", () => {
    expect(carbStatus(null, 420, 700)).toBe("No carbohydrate logged yet today.")
    expect(carbStatus(120, 420, 700)).toBe("120 g logged so far: 300 to 580 g more reaches the day's range.")
    expect(carbStatus(500, 420, 700)).toBe("500 g logged so far: within the day's range.")
    expect(carbStatus(750.4, 420, 700)).toBe("750 g logged so far: 50 g above the day's range.")
    expect(range(0, 0, "g")).toBe("0 g")
  })
})

describe("Fueling", () => {
  it("shows the session's carbs per hour, the day's range and what is logged, and syncs", async () => {
    const calls: string[] = []
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      calls.push(url)
      if (url === "/api/fueling") return json(BASE)
      if (url === "/api/nutrition/sync") return json({ start: "2026-09-19", end: "2026-10-18", days_with_data: 3, synced_at: "2026-10-18T10:00:00" })
      return json({}, 404)
    }))
    render(<Fueling />)
    expect(await screen.findByText("Planned: long z2, 3 h 00 min.")).toBeTruthy()
    expect(screen.getByText(/About 180 to 270 g over the session/)).toBeTruthy()
    expect(screen.getByText("High day (1 to 3 h): 6 to 10 g/kg, which is 420 to 700 g at 70 kg.")).toBeTruthy()
    expect(screen.getByText("120 g logged so far: 300 to 580 g more reaches the day's range.")).toBeTruthy()
    expect(screen.getByText("500 ml")).toBeTruthy()
    expect(screen.getByText("Not medical advice.")).toBeTruthy()
    await userEvent.click(screen.getByRole("button", { name: "Sync from SparkyFitness" }))
    expect(calls.filter((u) => u === "/api/fueling").length).toBeGreaterThanOrEqual(2)
  })

  it("on a rest day without a tracker it says so and points to Settings", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json({
      ...BASE, session: null, during: null, logged: null, connected: false,
      day: { load: "light", low_g_per_kg: 3, high_g_per_kg: 5, low_g: 210, high_g: 350 },
    })))
    render(<Fueling />)
    expect(await screen.findByText("No session planned today.")).toBeTruthy()
    expect(screen.getByText("Light day: 3 to 5 g/kg, which is 210 to 350 g at 70 kg.")).toBeTruthy()
    expect(screen.getByText(/Connect SparkyFitness in/)).toBeTruthy()
    expect(screen.queryByRole("button", { name: "Sync from SparkyFitness" })).toBeNull()
  })
})
