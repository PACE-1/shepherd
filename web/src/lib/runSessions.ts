import type { RunSession, RunSessions } from "@/api/types"
import { api } from "@/lib/api"
import { paceRange } from "@/lib/run"

// The run library (src/sessions_run.py, routes_run_sessions.py). Targets are % of threshold pace with the
// s/km they give, or an effort cue when no threshold pace is saved; `zone` is the intended Friel zone.
export interface RunTarget {
  kind: "pace_pct_threshold" | "effort"
  zone: string
  label?: string
  fast_s_per_km?: number | null
  slow_s_per_km?: number | null
}
interface Block {
  duration_s: number
  target: RunTarget
}
export type RunStep = ({ kind: "warmup" | "work" | "recovery" | "cooldown" } & Block) | { kind: "repeat"; count: number; on: Block; off: Block }

export interface RunQuery {
  type: string
  minMinutes: number | null
  maxMinutes: number | null
  maxRtss: number | null
}
export const EMPTY_QUERY: RunQuery = { type: "", minMinutes: null, maxMinutes: null, maxRtss: null }

export const RUN_TYPES: [string, string][] = [
  ["recovery", "Recovery"],
  ["aerobic", "Aerobic: easy and long"],
  ["threshold", "Threshold: tempo and cruise"],
  ["vo2max", "VO2max: intervals and hills"],
  ["speed", "Speed: strides"],
]

export function runQueryString(q: RunQuery): string {
  const p = new URLSearchParams()
  if (q.type) p.set("type", q.type)
  if (q.minMinutes !== null) p.set("min_minutes", String(q.minMinutes))
  if (q.maxMinutes !== null) p.set("max_minutes", String(q.maxMinutes))
  if (q.maxRtss !== null) p.set("max_rtss", String(q.maxRtss))
  const s = p.toString()
  return s ? `?${s}` : ""
}

export const listRunSessions = (q: RunQuery) => api<RunSessions>(`/api/run/sessions${runQueryString(q)}`)
export const getRunSession = (id: string, minutes: number) =>
  api<RunSession>(`/api/run/sessions/${encodeURIComponent(id)}?minutes=${minutes}`)
export const runDownloadUrl = (id: string, minutes: number, format: "fit" | "txt") =>
  `/api/run/sessions/${encodeURIComponent(id)}/download?minutes=${minutes}&format=${format}`

const dur = (s: number) => (s >= 60 ? `${Math.floor(s / 60)} min${s % 60 ? ` ${s % 60} s` : ""}` : `${s} s`)

export function targetText(t: RunTarget): string {
  if (t.kind === "effort") return `${t.label ?? ""} (Z${t.zone}, by feel)`
  return `${paceRange(t.slow_s_per_km, t.fast_s_per_km)} (Z${t.zone})`
}

const STEP: Record<string, string> = { warmup: "Warm-up", work: "Run", recovery: "Recovery", cooldown: "Cool-down" }

/** One line per step, as the plain-text download reads. */
export function stepLines(steps: RunStep[]): string[] {
  return steps.map((s) =>
    s.kind === "repeat"
      ? `${s.count} x ${dur(s.on.duration_s)} at ${targetText(s.on.target)}, then ${dur(s.off.duration_s)} at ${targetText(s.off.target)}`
      : `${STEP[s.kind]} ${dur(s.duration_s)}: ${targetText(s.target)}`,
  )
}
