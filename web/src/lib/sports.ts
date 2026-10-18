import type { SportThresholds, SportsLoad } from "@/api/types"
import { api } from "@/lib/api"

export const getSportsLoad = () => api<SportsLoad>("/api/sports/load")
export const getSportThresholds = () => api<SportThresholds>("/api/sports/thresholds")
export const setSportThreshold = (kind: string, value: number) =>
  api<SportThresholds>("/api/sports/thresholds", { method: "POST", json: { kind, value } })

/** "4:30" or "270" -> seconds; null when it is neither. */
export function parseClock(text: string): number | null {
  const m = /^\s*(?:(\d+):([0-5]\d)|(\d+))\s*$/.exec(text)
  if (!m) return null
  return m[3] !== undefined ? Number(m[3]) : Number(m[1]) * 60 + Number(m[2])
}

export const formatClock = (s: number) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`
