import type { PowerModel, RideCompare, WeightTrend } from "@/api/types"
import { api } from "@/lib/api"

export const getWeightTrend = (days: number) => api<WeightTrend>(`/api/analytics/weight-trend?days=${days}`)
export const getPowerModel = (days: number) => api<PowerModel>(`/api/analytics/power-model?window_days=${days}`)

/** An effort is a time range of a ride, in seconds from its start; leave both out for the whole ride. */
export interface Effort {
  start?: number
  end?: number
}

export function compareUrl(a: string, b: string, ea: Effort = {}, eb: Effort = {}) {
  const q = new URLSearchParams({ a, b })
  const add = (k: string, v?: number) => {
    if (v != null) q.set(k, String(Math.round(v)))
  }
  add("a_start", ea.start)
  add("a_end", ea.end)
  add("b_start", eb.start)
  add("b_end", eb.end)
  return `/api/analytics/compare?${q}`
}
export const compareRides = (a: string, b: string, ea?: Effort, eb?: Effort) => api<RideCompare>(compareUrl(a, b, ea, eb))

export const compareRoute = (a: string, b?: string) => `#/compare/${encodeURIComponent(a)}${b ? `/${encodeURIComponent(b)}` : ""}`

/** Binned values to chart points: x in minutes from the start, gaps (null) left out. */
export const binnedPoints = (values: (number | null)[], binS: number) =>
  values.flatMap((y, i) => (y == null ? [] : [{ x: (i * binS) / 60, y }]))

/** A signed difference with its unit, or a dash when either side is missing. */
export function fmtDelta(n: number | null | undefined, unit = "", digits = 0) {
  if (n == null) return "—"
  const v = Number(n.toFixed(digits))
  return `${v > 0 ? "+" : v < 0 ? "−" : "±"}${Math.abs(v).toFixed(digits)}${unit}`
}

/** "12:30" style minutes:seconds, or h:mm:ss over an hour. */
export function fmtClock(s: number | null | undefined) {
  if (s == null) return "—"
  const t = Math.round(s)
  const h = Math.floor(t / 3600)
  const m = Math.floor((t % 3600) / 60)
  const sec = String(t % 60).padStart(2, "0")
  return h ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`
}

/** Effort bounds typed as minutes ("" = not set) to seconds; null when the range is unusable. */
export function effortFromMinutes(start: string, end: string): Effort | null {
  if (start === "" && end === "") return {}
  const s = start === "" ? 0 : Number(start)
  const e = end === "" ? undefined : Number(end)
  if (!Number.isFinite(s) || s < 0 || (e !== undefined && (!Number.isFinite(e) || e <= s))) return null
  return { start: s * 60, end: e === undefined ? undefined : e * 60 }
}
