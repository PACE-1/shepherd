import { cleanup, render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { EMPTY_QUERY, runQueryString, stepLines, targetText } from "@/lib/runSessions"
import { RunWorkouts } from "@/screens/RunWorkouts"

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })
const pace = (zone: string, fast: number | null, slow: number | null) => ({ kind: "pace_pct_threshold", zone, fast_s_per_km: fast, slow_s_per_km: slow })
const SESSION = (minutes: number) => ({
  id: "run-intervals", name: "Interval reps", kind: "intervals", session_type: "run_intervals", stimulus: "vo2max", daniels: "I",
  intent: "Hard 4-minute reps with equal jog recoveries (Daniels I).", hard: true, min_minutes: 45, max_minutes: 60, minutes,
  workout: { name: "Interval reps", description: "", steps: [
    { kind: "warmup", duration_s: 600, target: pace("2", 342, 387) },
    { kind: "repeat", count: 3, on: { duration_s: 240, target: pace("5b", 270, 288) }, off: { duration_s: 240, target: pace("1", 387, null) } },
    { kind: "cooldown", duration_s: (minutes - 34) * 60, target: pace("2", 342, 387) },
  ] },
  rtss_estimate: 64.5, profile: [{ x: 0, y: 82 }, { x: 10, y: 82 }, { x: 10, y: 107 }, { x: minutes, y: 82 }], source: "Daniels",
})
const LIST = (targets: string) => ({ threshold_pace_s_per_km: targets === "pace" ? 300 : null, targets, note: "n", method: "Daniels 3rd ed.", sessions: [SESSION(50)] })
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe("run session text", () => {
  it("builds the query and reads targets", () => {
    expect(runQueryString(EMPTY_QUERY)).toBe("")
    expect(runQueryString({ type: "threshold", minMinutes: 30, maxMinutes: null, maxRtss: 50 })).toBe("?type=threshold&min_minutes=30&max_rtss=50")
    expect(targetText(pace("1", 387, null) as never)).toBe("slower than 6:27 /km (Z1)")
    expect(targetText({ kind: "effort", zone: "4", label: "comfortably hard" })).toBe("comfortably hard (Z4, by feel)")
    expect(stepLines(SESSION(50).workout.steps as never)[1]).toBe("3 x 4 min at 4:30 to 4:48 /km (Z5b), then 4 min at slower than 6:27 /km (Z1)")
  })
})

describe("RunWorkouts", () => {
  it("stays closed until asked, filters, and previews a session at a chosen length with downloads", async () => {
    const urls: string[] = []
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      urls.push(url)
      if (url.startsWith("/api/run/sessions/run-intervals?minutes=")) return json(SESSION(Number(url.split("=")[1])))
      if (url.startsWith("/api/run/sessions")) return json(LIST("effort"))
      return json({}, 404)
    }))
    render(<RunWorkouts />)
    expect(urls).toEqual([])
    await userEvent.click(screen.getByRole("button", { name: "Show run workouts" }))
    expect(await screen.findByText(/not validated against recorded runs/)).toBeTruthy()
    expect(screen.getByText(/targets are effort cues/)).toBeTruthy()
    await userEvent.selectOptions(screen.getByLabelText("Stimulus"), "vo2max")
    expect(urls.at(-1)).toBe("/api/run/sessions?type=vo2max")
    const list = await screen.findByRole("list", { name: "Run workouts" })
    await userEvent.click(within(list).getByRole("button", { name: /Interval reps/ }))
    expect(screen.getByRole("img", { name: "Intensity profile, 50 minutes" })).toBeTruthy()
    expect(screen.getByRole("link", { name: "Download .fit" }).getAttribute("href")).toBe("/api/run/sessions/run-intervals/download?minutes=50&format=fit")
    const len = screen.getByLabelText("Length (min)")
    await userEvent.clear(len)
    await userEvent.type(len, "55")
    expect(await screen.findByRole("img", { name: "Intensity profile, 55 minutes" })).toBeTruthy()
    expect(screen.getByRole("link", { name: "Download text" }).getAttribute("href")).toBe("/api/run/sessions/run-intervals/download?minutes=55&format=txt")
    await userEvent.clear(len)
    await userEvent.type(len, "90")
    expect(screen.getByRole("alert").textContent).toContain("Choose 45 to 60 minutes.")
    expect(screen.queryByRole("link", { name: "Download .fit" })).toBeNull()
  })

  it("shows an error with a retry", async () => {
    let fail = true
    vi.stubGlobal("fetch", vi.fn(async () => (fail ? json({ error: "boom" }, 500) : json(LIST("pace")))))
    render(<RunWorkouts />)
    await userEvent.click(screen.getByRole("button", { name: "Show run workouts" }))
    expect((await screen.findByRole("alert")).textContent).toContain("Couldn’t load the run workouts")
    fail = false
    await userEvent.click(screen.getByRole("button", { name: "Retry" }))
    expect(await screen.findByText("Interval reps")).toBeTruthy()
    expect(screen.queryByText(/targets are effort cues/)).toBeNull()
  })
})
