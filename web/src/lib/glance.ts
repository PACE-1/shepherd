import type { PlanSession, PlanWeek } from "@/api/types"
import { sessionsOn, weekSessions } from "@/lib/home"

// Pure rules for the "At a glance" panel on Home. Plain words, no network.

export type Level = "ready" | "easy" | "rest" | "unknown"
export interface Status {
  level: Level
  headline: string
  why: string
}

// Form (TSB, fitness minus fatigue) at or below -30 is the "high risk" zone in Coggan's form zones as
// published by TrainingPeaks. A rule of thumb, moderate confidence: it only softens the verdict to
// "take it easy"; the app's own readiness check (HRV, sleep, resting HR) takes priority over it.
export const HIGH_FATIGUE_TSB = -30

export interface StatusInput {
  /** From /api/readiness: normal | tier_down | rest. Undefined when it could not be read. */
  severity?: string | null
  /** The readiness score is null when there is no wellness data to read. */
  score?: number | null
  /** Form from /api/rider-stats. */
  tsb: number | null
  /** What the plan says for today. "unknown" when the plan could not be read. */
  today: "unknown" | "no-plan" | "rest" | "session"
}

export function dayStatus(i: StatusInput): Status {
  if (i.severity === "rest")
    return { level: "rest", headline: "Rest today", why: "Your recovery numbers (sleep, resting heart rate and heart-rate variability) say your body needs a day off." }
  if (i.today === "rest")
    return { level: "rest", headline: "Rest today", why: "Your plan has a rest day. Rest is when your body adapts and gets stronger." }
  if (i.severity === "tier_down")
    return { level: "easy", headline: "Take it easy today", why: "Your recovery numbers are a bit low. Keep today's ride gentle, or swap it for an easy spin." }
  if (i.tsb !== null && i.tsb <= HIGH_FATIGUE_TSB)
    return { level: "easy", headline: "Take it easy today", why: "You have trained hard lately and are carrying a lot of tiredness. A gentle day helps you absorb the work." }
  if ((i.score ?? null) !== null || i.tsb !== null)
    return { level: "ready", headline: "Ready to train", why: "Your recovery looks fine and you are not overly tired. Go ahead with today's plan." }
  return { level: "unknown", headline: "Not enough data yet", why: "Shepherd can't read your recovery yet. Sync your rides and sleep from intervals.icu, or just go by feel." }
}

/** One-line explanation of each session type, in plain words. */
const SESSION_WORDS: Record<string, string> = {
  recovery: "very easy spin",
  z2: "easy endurance ride",
  tempo: "steady, moderately hard",
  sweetspot: "hard but sustainable",
  threshold: "hard intervals near your limit",
  overunder: "hard intervals that go up and down",
  vo2max: "very hard short intervals",
  sprint: "short all-out sprints",
  ftp_test: "fitness test (finds your FTP, the power you can hold for about an hour)",
}
export const sessionWords = (type: string) => SESSION_WORDS[type] ?? type.replace(/_/g, " ")

export type TodayPlan =
  | { kind: "unknown" }
  | { kind: "none" } // no plan at all
  | { kind: "rest" }
  | { kind: "sessions"; sessions: PlanSession[] }

export function todayPlan(weeks: PlanWeek[] | undefined, week: PlanWeek | undefined, today: string): TodayPlan {
  if (!weeks?.length || !week) return { kind: "none" } // no plan, or the plan has ended
  const s = sessionsOn(week, today).filter((x) => !x.dismissed_at && x.status !== "dismissed")
  return s.length ? { kind: "sessions", sessions: s } : { kind: "rest" }
}

export const isDone = (s: PlanSession) => (s.status ?? "").startsWith("done")

export interface Progress {
  done: number
  planned: number
}
/** `done` comes from /api/week-summary (rides that matched a planned session); `planned` is this plan week's sessions. */
export function weekProgress(week: PlanWeek | undefined, done: number | null | undefined): Progress | null {
  if (!week) return null
  const planned = weekSessions(week).filter((s) => !s.dismissed_at && s.status !== "dismissed").length
  return { planned, done: Math.min(done ?? 0, planned) }
}

export interface NextStep {
  label: string
  why: string
  href: string
}
export interface SetupState {
  /** null: could not be read, so do not nag about it. */
  connected: boolean | null
  riderSet: boolean | null
  hasPlan: boolean | null
}
/** The single most useful thing still to set up, or null when the basics are done. */
export function nextStep(s: SetupState): NextStep | null {
  if (s.connected === false)
    return { label: "Connect intervals.icu", why: "That is where your rides, sleep and heart-rate data come from.", href: "#/onboarding" }
  if (s.riderSet === false)
    return { label: "Enter your rider numbers", why: "Your FTP, weight and heart rates make every target in Shepherd fit you.", href: "#/onboarding" }
  if (s.hasPlan === false)
    return { label: "Create a training plan", why: "A plan tells you what to ride each day.", href: "#/plan" }
  return null
}
