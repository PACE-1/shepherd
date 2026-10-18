import type { CriticalSpeed, RunActivities, RunGap, RunZones } from "@/api/types"
import { api } from "@/lib/api"
import { formatClock } from "@/lib/sports"

export type Trial = { distance_m: number; time_s: number }

export const getRunZones = () => api<RunZones>("/api/run/zones")
export const getRunActivities = () => api<RunActivities>("/api/run/activities")
export const criticalSpeed = (trials: Trial[], save = false) =>
  api<CriticalSpeed>("/api/run/critical-speed", { method: "POST", json: { trials, save } })
export const gradeAdjusted = (pace: number, grade: number) =>
  api<RunGap>(`/api/run/gap?pace_s_per_km=${pace}&grade_pct=${grade}`)

/** A pace range like "4:45 to 5:23 /km"; an open end reads "slower than" or "faster than". */
export function paceRange(slow: number | null | undefined, fast: number | null | undefined): string {
  if (slow == null && fast != null) return `slower than ${formatClock(fast)} /km`
  if (fast == null && slow != null) return `faster than ${formatClock(slow)} /km`
  if (slow == null || fast == null) return ""
  return `${formatClock(fast)} to ${formatClock(slow)} /km`
}

export function bpmRange(low: number | null | undefined, high: number | null | undefined): string {
  if (low == null && high != null) return `below ${high} bpm`
  if (high == null && low != null) return `above ${low} bpm`
  if (low == null || high == null) return ""
  return `${low} to ${high} bpm`
}
