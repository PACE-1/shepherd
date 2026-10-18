import { describe, expect, it } from "vitest"

import type { PlanSession, PlanWeek } from "@/api/types"
import { dayStatus, nextStep, sessionWords, todayPlan, weekProgress } from "@/lib/glance"

const s = (day: string, over: Partial<PlanSession> = {}) =>
  ({ day, session_type: "z2", duration_min: 60, tss_estimate: 40, status: "pending", ...over }) as PlanSession
const week = (sessions: PlanSession[]) => ({ start: "2026-10-12", end: "2026-10-18", sessions }) as unknown as PlanWeek

describe("dayStatus", () => {
  it("says rest when readiness says rest, before anything else", () => {
    expect(dayStatus({ severity: "rest", tsb: 5, today: "session" }).level).toBe("rest")
  })
  it("says rest on a planned rest day", () => {
    expect(dayStatus({ severity: "normal", score: 80, tsb: 0, today: "rest" }).headline).toBe("Rest today")
  })
  it("says take it easy when readiness is reduced", () => {
    expect(dayStatus({ severity: "tier_down", tsb: 0, today: "session" }).headline).toBe("Take it easy today")
  })
  it("softens to easy at form -30 or lower, not above", () => {
    expect(dayStatus({ severity: "normal", score: 70, tsb: -30, today: "session" }).level).toBe("easy")
    expect(dayStatus({ severity: "normal", score: 70, tsb: -29, today: "session" }).level).toBe("ready")
  })
  it("is ready when recovery looks fine", () => {
    expect(dayStatus({ severity: "normal", score: 82, tsb: 3, today: "session" }).headline).toBe("Ready to train")
  })
  it("does not claim ready without any data", () => {
    expect(dayStatus({ severity: "normal", score: null, tsb: null, today: "session" }).level).toBe("unknown")
    expect(dayStatus({ tsb: null, today: "unknown" }).level).toBe("unknown")
  })
})

describe("todayPlan and weekProgress", () => {
  it("lists today's sessions, ignoring dismissed ones", () => {
    const w = week([s("2026-10-15"), s("2026-10-15", { status: "dismissed" })])
    const t = todayPlan([w], w, "2026-10-15")
    expect(t.kind === "sessions" && t.sessions.length).toBe(1)
  })
  it("is a rest day when the week has nothing today, and none without a plan or week", () => {
    const w = week([s("2026-10-16")])
    expect(todayPlan([w], w, "2026-10-15").kind).toBe("rest")
    expect(todayPlan([], undefined, "2026-10-15").kind).toBe("none")
    expect(todayPlan([w], undefined, "2026-10-15").kind).toBe("none")
  })
  it("counts planned rides, skipping rest and dismissed, and clamps done", () => {
    const w = week([s("2026-10-12"), s("2026-10-13", { session_type: "rest" }), s("2026-10-14"), s("2026-10-15", { status: "dismissed" })])
    expect(weekProgress(w, 1)).toEqual({ done: 1, planned: 2 })
    expect(weekProgress(w, 5)).toEqual({ done: 2, planned: 2 })
    expect(weekProgress(w, null)).toEqual({ done: 0, planned: 2 })
    expect(weekProgress(undefined, 1)).toBeNull()
  })
})

describe("nextStep and words", () => {
  it("names the first missing setup step, and nothing when unreadable or complete", () => {
    expect(nextStep({ connected: false, riderSet: false, hasPlan: false })?.label).toBe("Connect intervals.icu")
    expect(nextStep({ connected: true, riderSet: false, hasPlan: false })?.label).toBe("Enter your rider numbers")
    expect(nextStep({ connected: true, riderSet: true, hasPlan: false })?.href).toBe("#/plan")
    expect(nextStep({ connected: true, riderSet: true, hasPlan: true })).toBeNull()
    expect(nextStep({ connected: null, riderSet: null, hasPlan: null })).toBeNull()
  })
  it("explains session types in plain words, with a fallback", () => {
    expect(sessionWords("z2")).toBe("easy endurance ride")
    expect(sessionWords("some_new_type")).toBe("some new type")
  })
})
