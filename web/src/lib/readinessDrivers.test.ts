import { describe, expect, it } from "vitest"

import type { Readiness, SportsLoad } from "@/api/types"
import { readinessDrivers, recentLoadByType } from "@/lib/readinessDrivers"

const r = (extra: Record<string, unknown>) => ({ severity: "normal", severity_reasons: [], ...extra }) as unknown as Readiness
const line = (week_load: number) => ({ ctl: 1, atl: 1, tsb: 0, week_load })

describe("readinessDrivers", () => {
  it("names each input that scored, with its value and where the form comes from", () => {
    const text = readinessDrivers(
      r({
        readiness: { components: { hrv: 60, tsb: 50, sleep: 70, rhr: 80, subjective: 50 } },
        sleep: { hrv_status: "RED", rhr_delta: 4.25, sleep_h: 6.14 },
        training: { tsb: -8.04, source: "icu" },
      }),
    )
    expect(text).toBe(
      "Today’s score used: your 7-day HRV is below your baseline range; resting heart rate +4.3 bpm against your 7-day average; 6.1 h of sleep; form -8 (from intervals.icu, all sports); your daily check-in.",
    )
  })

  it("leaves out inputs that did not go into the score", () => {
    const text = readinessDrivers(r({ readiness: { components: { tsb: 50 } }, sleep: { sleep_h: 8 }, training: { tsb: 3 } }))
    expect(text).toBe("Today’s score used: form +3.")
  })

  it("says nothing when there is no component", () => {
    expect(readinessDrivers(r({ readiness: { components: {} } }))).toBe("")
    expect(readinessDrivers(r({}))).toBe("")
  })
})

describe("recentLoadByType", () => {
  it("orders sports by the last 7 days of load and carries the total", () => {
    const load = { sports: { cycling: line(120), swimming: line(30), running: line(80) }, combined: line(230) } as unknown as SportsLoad
    const { rows, total } = recentLoadByType(load)
    expect(rows.map((x) => [x.name, x.load])).toEqual([["Cycling", 120], ["Running", 80], ["Swimming", 30]])
    expect(total).toBe(230)
  })
})
