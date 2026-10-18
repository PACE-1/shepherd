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

export type SportKind = "cycling" | "running" | "swimming" | "other"

const KIND: Record<string, SportKind> = {
  ...Object.fromEntries(["ride", "virtualride", "gravelride", "mountainbikeride", "ebikeride", "ebikemountainbikeride", "handcycle", "velomobile"].map((k) => [k, "cycling"])),
  ...Object.fromEntries(["run", "trailrun", "virtualrun", "walk", "hike"].map((k) => [k, "running"])),
  ...Object.fromEntries(["swim", "openwaterswim"].map((k) => [k, "swimming"])),
}

/** Mirrors multisport.sport_of on the server. A ride with no recorded type (a FIT import) is cycling, as it always was. */
export function sportKind(type: string | null | undefined): SportKind {
  if (!type) return "cycling"
  return KIND[type.replace(/[ _]/g, "").toLowerCase()] ?? "other"
}

/** Average pace over the whole activity: seconds per km for running, per 100 m for swimming. Null without time and distance. */
export function averagePace(kind: SportKind, durationS: number | null | undefined, distanceKm: number | null | undefined): number | null {
  if (!durationS || !distanceKm || durationS <= 0 || distanceKm <= 0) return null
  return kind === "swimming" ? durationS / (distanceKm * 10) : durationS / distanceKm
}
