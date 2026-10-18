import type { BrickTransition, CompanionDismissed, PlanCompanion, PlanCompanions } from "@/api/types"
import { api } from "@/lib/api"

// Companion sessions: runs, swims and strength the planner adds next to the cycling plan when the rider's
// sport targets give another sport a share (src/multisport_plan.py).
export const getCompanions = (start?: string) =>
  api<PlanCompanions>(start ? `/api/plan/companions?start=${encodeURIComponent(start)}` : "/api/plan/companions")

export const dismissCompanion = (id: string) =>
  api<CompanionDismissed>(`/api/plan/companions/${encodeURIComponent(id)}/dismiss`, { method: "POST" })

export const NOT_VALIDATED = "Not validated against real runs/swims yet."

const SPORT: Record<string, string> = { running: "Run", swimming: "Swim", strength: "Strength" }
export const sportLabel = (sport: string) => SPORT[sport] ?? sport

/** The label a companion is shown with: a brick run and a mobility session get their own. */
export const companionLabel = (c: PlanCompanion) =>
  c.brick_of ? "Brick run" : c.session_type === "mobility" ? "Mobility" : sportLabel(c.sport)

// Bricks (#123): the rider's transition-time target (no default) and a note on the run off the bike.
export const saveTransition = (seconds: number | null) =>
  api<BrickTransition>("/api/plan/bricks/transition", { method: "PUT", json: { transition_target_s: seconds } })

export const saveBrickNote = (id: string, note: string) =>
  api<CompanionDismissed>(`/api/plan/companions/${encodeURIComponent(id)}/brick-note`, { method: "POST", json: { note } })

/** Seconds as m:ss. */
export const fmtClock = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`

/** "m:ss" or whole seconds to seconds; "" is null (cleared); anything else, or outside 1 s to 60 min, is undefined. */
export function parseClock(v: string): number | null | undefined {
  const t = v.trim()
  if (t === "") return null
  const m = /^(\d{1,2}):([0-5]\d)$/.exec(t)
  const s = m ? Number(m[1]) * 60 + Number(m[2]) : /^\d+$/.test(t) ? Number(t) : NaN
  return s >= 1 && s <= 3600 ? s : undefined
}

const STATUS: Record<string, string> = { done: "done", missed: "missed", dismissed: "dismissed" }
export const companionStatus = (c: PlanCompanion) => STATUS[c.status ?? ""] ?? ""

/** The companions of the plan week starting on ``start``; empty for an unexpected payload. */
export const weekCompanions = (data: PlanCompanions | undefined, start: string): PlanCompanion[] => {
  const weeks = Array.isArray(data?.weeks) ? data.weeks : []
  const week = weeks.find((w) => w.start === start)
  return Array.isArray(week?.companions) ? week.companions : []
}
