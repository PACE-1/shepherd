import type { BuilderLoaded, BuilderPreview, BuilderPush, BuilderSaved } from "@/api/types"
import { api } from "@/lib/api"

// The workout model the server validates (src/workout_builder.py). `target.kind` is open to pace later.
export type TargetKind = "power" | "hr"
export interface Target {
  kind: TargetKind
  lo: number
  hi: number
}
export interface Block {
  duration_s: number
  target: Target
  cadence_note: string
}
export type TimedKind = "warmup" | "work" | "recovery" | "cooldown"
export type Step = ({ kind: TimedKind } & Block) | { kind: "repeat"; count: number; on: Block; off: Block }
export interface Workout {
  name: string
  description: string
  steps: Step[]
}
/** A step as the screen holds it: `uid` keeps React keys stable while steps move; it never goes to the server. */
export type UiStep = Step & { uid: number }

export const KIND_LABEL: Record<Step["kind"], string> = {
  warmup: "Warm-up",
  work: "Work",
  recovery: "Recovery",
  cooldown: "Cool-down",
  repeat: "Repeat",
}
export const TARGET_UNIT: Record<TargetKind, string> = { power: "% FTP", hr: "% LTHR" }

let nextUid = 1
export const withUid = (s: Step): UiStep => ({ ...s, uid: nextUid++ })

const power = (lo: number, hi = lo): Target => ({ kind: "power", lo, hi })
const block = (duration_s: number, target: Target): Block => ({ duration_s, target, cadence_note: "" })

/** A fresh step of the given kind with a typical target. */
export function newStep(kind: Step["kind"]): UiStep {
  switch (kind) {
    case "warmup":
      return withUid({ kind, ...block(600, power(50, 70)) })
    case "cooldown":
      return withUid({ kind, ...block(300, power(40, 55)) })
    case "recovery":
      return withUid({ kind, ...block(180, power(50)) })
    case "work":
      return withUid({ kind, ...block(600, power(90)) })
    case "repeat":
      return withUid({ kind, count: 4, on: block(240, power(105)), off: block(240, power(50)) })
  }
}

export const startingSteps = (): UiStep[] => [newStep("warmup"), newStep("repeat"), newStep("cooldown")]

export function move<T>(list: T[], i: number, by: -1 | 1): T[] {
  const j = i + by
  if (j < 0 || j >= list.length) return list
  const out = list.slice()
  ;[out[i], out[j]] = [out[j], out[i]]
  return out
}

export const toWire = (name: string, description: string, steps: UiStep[]): Workout => ({
  name,
  description,
  steps: steps.map((s) => {
    const wire: Partial<UiStep> = { ...s }
    delete wire.uid
    return wire as Step
  }),
})

export const fmtClock = (s: number) => {
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}` : `${m}:${String(sec).padStart(2, "0")}`
}

export const preview = (workout: Workout) => api<BuilderPreview>("/api/builder/preview", { method: "POST", json: { workout } })
export const save = (workout: Workout, file?: string) =>
  api<BuilderSaved>("/api/builder/save", { method: "POST", json: { workout, file } })
export const send = (workout: Workout, date: string, file?: string) =>
  api<BuilderSaved>("/api/builder/send", { method: "POST", json: { workout, date, file } })
export const loadWorkout = (file: string) => api<BuilderLoaded>(`/api/builder/workout?file=${encodeURIComponent(file)}`)

const PUSH_ERRORS: Record<string, string> = {
  not_connected: "intervals.icu isn't connected. Connect it in Settings first.",
  no_active_profile: "There is no active profile.",
  bad_date: "That isn't a valid date.",
  date_out_of_range: "Pick a date from today to a year ahead.",
  network: "Couldn't reach intervals.icu. Check your connection and try again.",
  busy: "A calendar sync is running. Try again in a minute.",
  file_missing: "The saved workout file couldn't be found.",
  build_failed: "The workout couldn't be converted for your head unit.",
  trailing_open: "The workout ends on an open step, which intervals.icu drops. End it on a timed step.",
}

/** What to tell the rider about the push. The workout itself is already saved in every case. */
export function pushMessage(p: BuilderPush | null | undefined, date: string): { ok: boolean; text: string } {
  if (p?.ok) return { ok: true, text: `Sent to your intervals.icu calendar for ${date}.` }
  if (p?.needs_reconnect)
    return { ok: false, text: "intervals.icu hasn't given Shepherd permission to write to your calendar. Reconnect it in Settings, then send again." }
  if (p?.needs_lthr)
    return { ok: false, text: "Your profile uses heart-rate targets but has no valid threshold heart rate. Set it in Settings, then send again." }
  const code = p?.error ?? "unknown"
  const text = PUSH_ERRORS[code] ?? (code.startsWith("http_") ? `intervals.icu refused it (${code.replace("_", " ")}).` : `Couldn't send it (${code}).`)
  return { ok: false, text }
}
