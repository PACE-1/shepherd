import { afterEach, describe, expect, it, vi } from "vitest"

import type { PlanRead, SettingsRead } from "@/api/types"
import { aiCheck, EMPTY, firstOpen, goalCheck, icuCheck, markDone, markSkipped, readProgress, riderCheck, riderPayload, STEPS, stateOf, writeProgress } from "@/lib/onboarding"

afterEach(() => { localStorage.clear(); vi.restoreAllMocks() })

describe("progress", () => {
  it("moves the open step along as steps are done or skipped, and finishes when all are", () => {
    let p = markDone(EMPTY, "icu")
    expect(stateOf(p, "icu")).toBe("done")
    expect(STEPS[firstOpen(p)].id).toBe("rider")
    p = markSkipped(p, "rider")
    expect(STEPS[firstOpen(p)].id).toBe("ai")
    for (const s of STEPS) p = markDone(p, s.id)
    expect(p.finished).toBe(true)
    expect(markSkipped(p, "ai").finished).toBe(true)
  })
  it("redoing a skipped step moves it to done", () => {
    const p = markDone(markSkipped(EMPTY, "ai"), "ai")
    expect(p.skipped).toEqual([])
    expect(p.done).toEqual(["ai"])
  })
  it("round-trips through localStorage and survives broken or blocked storage", () => {
    writeProgress("k", markDone(EMPTY, "icu"))
    expect(readProgress("k").done).toEqual(["icu"])
    localStorage.setItem("k", "{not json")
    expect(readProgress("k")).toEqual(EMPTY)
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked") })
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked") })
    expect(readProgress("k")).toEqual(EMPTY)
    expect(() => writeProgress("k", EMPTY)).not.toThrow()
  })
})

describe("checks", () => {
  it("block until the step is really complete", () => {
    expect(icuCheck({ connected: false } as never)).toMatch(/not connected/)
    expect(icuCheck({ connected: true } as never)).toBeNull()
    expect(riderCheck({ lthr_is_set: false } as SettingsRead)).toMatch(/Save your rider numbers/)
    expect(riderCheck({ lthr_is_set: true } as SettingsRead)).toBeNull()
    expect(aiCheck({ configured: false } as never)).toMatch(/No AI provider/)
    expect(goalCheck({ plan_json: { weeks: [] } } as unknown as PlanRead)).toMatch(/Create a training plan/)
    expect(goalCheck({ plan_json: { weeks: [{}] } } as unknown as PlanRead)).toBeNull()
  })
  it("sends every rider number as a number", () => {
    expect(riderPayload({ weight: "70", ftp: "250", lthr: "170", maxHr: "190", targetMode: "hr" })).toEqual({
      weight: 70, ftp: 250, lthr: 170, max_hr: 190, target_mode: "hr",
    })
  })
})
