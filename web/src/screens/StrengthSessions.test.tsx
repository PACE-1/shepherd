import { cleanup, render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { StrengthSessions } from "@/screens/StrengthSessions"

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

const NOTE = "arbitrary units (session-RPE), not comparable with TSS"
const ex = (id: string, name: string, o: object = {}) => ({
  id, name, pattern: "squat", cue: `Cue for ${name}.`, per_side: false, sets: [1, 3], reps: [8, 12], hold_s: null, rpe: [4, 6],
  effort: "Moderate.", rest: "1-2 minutes between sets", ...o,
})
const session = (id: string, name: string, o: object = {}) => ({
  id, name, kind: "strength", intent: `${name} intent.`, minutes: 45, minutes_range: [30, 45], stage: "novice", stage_label: "Novice",
  hard: false, exercises: [ex("a", "Goblet squat"), ex("b", "Front plank", { reps: null, hold_s: 30, per_side: false })],
  rpe_range: [4, 6], load_au: [180, 270], load_note: NOTE, load_method: "Session-RPE method.",
  progression: { sets: [1, 3], reps: [8, 12], rest: "1-2 minutes between sets", pct_1rm: "about 60-70% of 1RM", verify: false },
  warmup_min: 5, disclaimer: "D", not_validated: "NV", source: "ACSM 2009", ...o,
})
const stages = [
  { id: "novice", label: "Novice", sets: [1, 3], reps: [8, 12], rpe: [4, 6], effort: "Moderate.", rest: "r", pct_1rm: "p", source: "s", verify: false },
  { id: "experienced", label: "Experienced", sets: [3, 4], reps: [4, 6], rpe: [6, 8], effort: "Hard.", rest: "r", pct_1rm: "p", source: "s", verify: true },
]
const body = (stage: string) => ({
  stage, stages, sessions: [session("sa", "Strength A"), session("mob", "Mobility", { kind: "mobility", warmup_min: 0, progression: null })],
  disclaimer: "General fitness guidance, not individual medical or coaching advice. Stop if anything hurts.",
  not_validated: "NV", load_note: NOTE, load_method: "m", sources: ["ACSM 2009", "Foster 2001"],
})

function server() {
  const urls: string[] = []
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    urls.push(url)
    const stage = new URL(url, "http://x").searchParams.get("stage") ?? "novice"
    return json(body(stage))
  }))
  return urls
}

describe("StrengthSessions", () => {
  it("lists the exercises with sets, reps, holds and the load unit text", async () => {
    server()
    render(<StrengthSessions />)
    const a = await screen.findByRole("article", { name: "Strength A" })
    expect(within(a).getByText(/1\. Goblet squat/)).toBeTruthy()
    expect(within(a).getByText(/^: 1-3 sets of 8-12 repetitions$/)).toBeTruthy()
    expect(within(a).getByText(/1-3 holds of 30 s/)).toBeTruthy()
    expect(within(a).getByText(/Cue for Goblet squat/)).toBeTruthy()
    expect(within(a).getByText(/180-270 arbitrary units \(session-RPE\), not comparable with TSS/)).toBeTruthy()
    expect(screen.getAllByRole("note")[0].textContent).toContain("not individual medical or coaching advice")
    expect(screen.getByRole("button", { name: "Print this session" })).toBeTruthy()
  })

  it("switches session and reloads for another stage", async () => {
    const urls = server()
    render(<StrengthSessions />)
    await screen.findByRole("article", { name: "Strength A" })
    await userEvent.click(screen.getByRole("button", { name: "Mobility" }))
    expect(screen.getByRole("article", { name: "Mobility" })).toBeTruthy()
    await userEvent.selectOptions(screen.getByLabelText("Training stage"), "experienced")
    await screen.findByText(/not checked against the paper yet/)
    expect(urls.at(-1)).toBe("/api/strength/sessions?stage=experienced")
  })

  it("prints the chosen session", async () => {
    server()
    const print = vi.fn()
    vi.stubGlobal("print", print)
    render(<StrengthSessions />)
    await userEvent.click(await screen.findByRole("button", { name: "Print this session" }))
    expect(print).toHaveBeenCalledOnce()
  })
})
