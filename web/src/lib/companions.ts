import type { CompanionDismissed, PlanCompanion, PlanCompanions } from "@/api/types"
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

const STATUS: Record<string, string> = { done: "done", missed: "missed", dismissed: "dismissed" }
export const companionStatus = (c: PlanCompanion) => STATUS[c.status ?? ""] ?? ""

/** The companions of the plan week starting on ``start``; empty for an unexpected payload. */
export const weekCompanions = (data: PlanCompanions | undefined, start: string): PlanCompanion[] => {
  const weeks = Array.isArray(data?.weeks) ? data.weeks : []
  const week = weeks.find((w) => w.start === start)
  return Array.isArray(week?.companions) ? week.companions : []
}
