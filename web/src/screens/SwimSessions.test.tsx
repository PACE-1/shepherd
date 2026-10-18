import { cleanup, render, screen, within } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { rangeLabel, sessionTextUrl } from "@/lib/swimSessions"
import { SwimSessions } from "@/screens/SwimSessions"

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })
const DATA = (css: number | null) => ({
  css_s_per_100m: css,
  has_css: css != null,
  pool_m: 25,
  source: "CSS: Wakayoshi et al. 1992 and 1993. The set shapes are common coaching practice templates, not a validated protocol.",
  not_validated: "Not validated against real recorded swims yet.",
  download_note: "Plain text only: no FIT or watch file is made for swim sessions.",
  sessions: [
    { id: "swim-recovery", name: "Recovery swim", kind: "recovery", session_type: "swim_endurance", intent: "Short, loose recovery swim.", hard: false, minutes: 30, minutes_min: 20, minutes_max: 40, lines: ["30 min of easy swimming, mixing strokes freely."], note: "" },
    {
      id: "swim-css-intervals", name: "CSS intervals", kind: "css", session_type: "swim_css", intent: "Repeats of 100-200 m at CSS pace.", hard: true, minutes: 55, minutes_min: 40, minutes_max: 70, note: "",
      lines: css ? ["Warm-up 16 min.", "Main set: 9 x 200 m at CSS (1:35 per 100 m), 20 s rest.", "Cool-down 9 min."] : ["Warm-up 14 min.", "Main set: 6 x 200 m, 20 s rest, effort comfortably hard.", "Cool-down 8 min."],
    },
  ],
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe("swim sessions text", () => {
  it("builds the download link and the range label", () => {
    expect(sessionTextUrl("swim-css-intervals")).toBe("/api/swim/sessions/swim-css-intervals/text")
    expect(rangeLabel(40, 70)).toBe("40-70 min")
  })
})

describe("SwimSessions", () => {
  it("lists the sets for the saved CSS, with a plain-text download and the not-validated notes", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json(DATA(95))))
    render(<SwimSessions />)
    expect(await screen.findByText(/Sets are written for your CSS, 1:35 \/100 m/)).toBeTruthy()
    const list = screen.getByRole("list", { name: "CSS intervals sets" })
    expect(within(list).getByText(/9 x 200 m at CSS \(1:35 per 100 m\), 20 s rest/)).toBeTruthy()
    expect(screen.getByText(/30 min of easy swimming/)).toBeTruthy()
    expect(screen.getByRole("link", { name: "Download CSS intervals as text" }).getAttribute("href")).toBe("/api/swim/sessions/swim-css-intervals/text")
    expect(screen.getByText(/no FIT or watch file/)).toBeTruthy()
    expect(screen.getByText(/not a validated protocol/)).toBeTruthy()
    expect(screen.getByText(/Not validated against real recorded swims/)).toBeTruthy()
    expect(screen.getByText(/25 m pool assumed/)).toBeTruthy()
  })

  it("without a CSS says the sets have no times", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json(DATA(null))))
    render(<SwimSessions />)
    expect(await screen.findByText(/No swim CSS yet, so sets show metres and an effort, without times/)).toBeTruthy()
    expect(screen.getByText(/6 x 200 m, 20 s rest, effort comfortably hard/)).toBeTruthy()
  })

  it("shows an error with a retry when the sessions cannot be loaded", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json({ detail: "boom" }, 500)))
    render(<SwimSessions />)
    expect(await screen.findByRole("alert")).toBeTruthy()
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy()
  })
})
