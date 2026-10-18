import { describe, expect, it } from "vitest"

import type { GenerateRequest } from "@/lib/home"
import { advancedProblem, applyAdvanced, NO_ADVANCED, type Advanced } from "@/lib/planForm"

const base: GenerateRequest = { goal: "ftp", hours_per_week: 8, plan_weeks: 12, rest_days: [0] }
const adv = (over: Partial<Advanced>): Advanced => ({ ...NO_ADVANCED, ...over })
const today = "2026-10-16"

describe("applyAdvanced", () => {
  it("sends exactly what it was given when nothing was touched", () => {
    expect(applyAdvanced(base, NO_ADVANCED, null)).toEqual(base)
  })

  it("adds only the options that differ from the defaults", () => {
    const r = applyAdvanced(base, adv({ distribution: "pyramidal", block: true, mode: "template", template: "ftp_builder" }), null)
    expect(r).toEqual({ ...base, distribution: "pyramidal", block_periodization: true, plan_mode: "template", template_id: "ftp_builder" })
  })

  it("sends custom shares as numbers and only for the custom template", () => {
    const r = applyAdvanced(base, adv({ mode: "template", template: "custom", bands: { tempo_ss: "10", threshold: "5", vo2: "", sprint: "0" } }), null)
    expect(r.custom_bands).toEqual({ tempo_ss: 10, threshold: 5, vo2: 0, sprint: 0 })
    expect(applyAdvanced(base, adv({ mode: "template", template: "ftp_builder", bands: { tempo_ss: "10", threshold: "", vo2: "", sprint: "" } }), null).custom_bands).toBeUndefined()
  })

  it("derives hours, limits and rest days from per-day hours", () => {
    const r = applyAdvanced(base, adv({ useDayHours: true, dayHours: ["0", "1", "1", "1.5", "1", "3", "4"] }), null)
    expect(r).toMatchObject({ daily_availability: { 0: 0, 1: 1, 2: 1, 3: 1.5, 4: 1, 5: 3, 6: 4 }, hours_per_week: 11.5, max_weekday: 1.5, max_weekend: 4, rest_days: [0] })
  })

  it("marks a backdated start as declared, or recognized when it came from the ride scan", () => {
    expect(applyAdvanced(base, adv({ backdate: true, startDate: "2026-09-01" }), null)).toMatchObject({ start_date: "2026-09-01", entry_mode: "declared" })
    expect(applyAdvanced(base, adv({ backdate: true, startDate: "2026-09-01", recognized: true }), null)).toMatchObject({ entry_mode: "recognized" })
    expect(applyAdvanced(base, adv({ backdate: false, startDate: "2026-09-01" }), null).start_date).toBeUndefined()
  })

  it("keeps the A race in the goal fields and sends only B and C races in events", () => {
    const ev: GenerateRequest = { goal: "event", hours_per_week: 8, plan_weeks: 12, rest_days: [], event_name: "Fondo", event_date: "2027-06-01" }
    const r = applyAdvanced(ev, adv({ eventKm: "120", races: [{ date: "2027-04-01", name: "Crit", priority: "C" }] }), null)
    expect(r.events).toEqual([{ date: "2027-04-01", priority: "C", name: "Crit" }])
    expect(r).toMatchObject({ event_name: "Fondo", event_date: "2027-06-01", event_km: 120, event_type: "granfondo" })
  })

  it("sends B and C races alone for a goal without an event, and an end date as the event date", () => {
    const r = applyAdvanced(base, adv({ endDate: "2027-01-01", races: [{ date: "2026-12-01", name: "", priority: "B" }] }), null)
    expect(r.events).toEqual([{ date: "2026-12-01", priority: "B", name: "" }])
    expect(r.event_date).toBe("2027-01-01")
  })

  it("sends a phase split only when it differs from the recommendation", () => {
    const rec = { base: 4, build1: 4 }
    expect(applyAdvanced(base, adv({ phaseWeeks: { base: "4", build1: "4" } }), rec).phase_weeks).toBeUndefined()
    expect(applyAdvanced(base, adv({ phaseWeeks: { base: "5", build1: "3" } }), rec).phase_weeks).toEqual({ base: 5, build1: 3 })
  })

  it("sends the focus only for a continuous plan", () => {
    expect(applyAdvanced({ ...base, goal: "continuous" }, adv({ focus: "ftp" }), null).focus).toBe("ftp")
    expect(applyAdvanced(base, adv({ focus: "ftp" }), null).focus).toBeUndefined()
  })
})

describe("advancedProblem", () => {
  it("accepts the defaults", () => expect(advancedProblem(NO_ADVANCED, "ftp", today)).toBe(""))
  it("names each kind of problem", () => {
    expect(advancedProblem(adv({ mode: "template", template: "custom", bands: { tempo_ss: "60", threshold: "50", vo2: "", sprint: "" } }), "ftp", today)).toMatch(/more than 100/)
    expect(advancedProblem(adv({ backdate: true, startDate: "" }), "ftp", today)).toMatch(/start date/)
    expect(advancedProblem(adv({ backdate: true, startDate: "2027-01-01" }), "ftp", today)).toMatch(/today or earlier/)
    expect(advancedProblem(adv({ useDayHours: true, dayHours: ["", "", "", "", "", "", ""] }), "ftp", today)).toMatch(/at least one day/)
    expect(advancedProblem(adv({ useDayHours: true, dayHours: ["20", "", "", "", "", "", ""] }), "ftp", today)).toMatch(/between 0 and 12/)
    expect(advancedProblem(adv({ races: [{ date: "2026-01-01", name: "", priority: "B" }] }), "ftp", today)).toMatch(/future/)
    expect(advancedProblem(adv({ endDate: "2026-01-01" }), "ftp", today)).toMatch(/end date/)
    expect(advancedProblem(adv({ phaseWeeks: { base: "0" } }), "ftp", today)).toMatch(/1 and 30/)
    expect(advancedProblem(adv({ eventKm: "0" }), "event", today)).toMatch(/distance/)
  })
})
