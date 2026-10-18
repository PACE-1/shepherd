import { describe, expect, it } from "vitest"

import { parseTargets, summarise } from "@/lib/balance"

const week = (start: string, c: number, r = 0) => ({
  key: start, label: start, start, end: start, load: {}, total_load: 0, hours_share: {}, load_share: {},
  hours: { cycling: c, running: r, swimming: 0, other: 0 }, total_hours: c + r,
})

describe("parseTargets", () => {
  it("is empty when nothing is typed, and treats blank boxes as 0 once one is filled", () => {
    expect(parseTargets({})).toEqual({ targets: null, error: "" })
    expect(parseTargets({ cycling: "70", running: "30" }).targets).toEqual({ cycling: 70, running: 30, swimming: 0, other: 0 })
  })
  it("refuses a split that does not add up to 100 or a value out of range", () => {
    expect(parseTargets({ cycling: "70", running: "20" }).error).toContain("add up to 90")
    expect(parseTargets({ cycling: "120" }).error).toContain("Cycling must be")
    expect(parseTargets({ cycling: "x" }).targets).toBeNull()
  })
})

describe("summarise", () => {
  it("states the period, the average week and the split", () => {
    const s = summarise([week("2026-10-05", 6, 2), week("2026-10-12", 4, 0)])
    expect(s).toContain("2 weeks from 2026-10-05")
    expect(s).toContain("12 h in all, 6 h a week")
    expect(s).toContain("cycling 83%, running 17%")
    expect(s).toContain("Biggest week 8 h, the week of 2026-10-05")
  })
  it("says so when there are no hours", () => {
    expect(summarise([week("2026-10-05", 0)])).toBe("No training hours in this period.")
  })
})
