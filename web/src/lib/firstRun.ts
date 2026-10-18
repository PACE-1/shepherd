import type { ActivitiesCheck, AthleteNumbers, PickedFolder } from "@/api/types"
import { api } from "@/lib/api"
import type { Limits, TargetMode } from "@/lib/setup"

// Field ids and the localStorage shape match the legacy first-run wizard, so a rider mid-setup keeps their state.
export const FIELD_IDS = [
  "s-weight", "s-ftp", "s-lthr", "s-maxhr", "s-age", "s-sex", "s-cp", "s-wprime",
  "s-workout-dir", "s-hours",
] as const
export type FieldId = (typeof FIELD_IDS)[number]

export interface WizardState {
  values: Record<FieldId, string>
  touched: FieldId[]
  icuOrigin: FieldId[]
  days: string[] // "0".."6", Monday first
  rest: string[]
  daysTouched: boolean
  restTouched: boolean
  targetMode: TargetMode
  targetModeTouched: boolean
}

export const INITIAL: WizardState = {
  values: {
    "s-weight": "72", "s-ftp": "250", "s-lthr": "175", "s-maxhr": "196", "s-age": "", "s-sex": "",
    "s-cp": "", "s-wprime": "", "s-workout-dir": "", "s-hours": "8",
  },
  touched: [],
  icuOrigin: [],
  days: ["1", "2", "3", "4", "5", "6"], // Mon is the default rest day
  rest: ["0"],
  daysTouched: false,
  restTouched: false,
  targetMode: "power",
  targetModeTouched: false,
}

const BOUNDS: Partial<Record<FieldId, { key: keyof Limits | "hours_per_week"; min: number; max: number }>> = {
  "s-weight": { key: "weight", min: 30, max: 200 },
  "s-ftp": { key: "ftp", min: 50, max: 600 },
  "s-lthr": { key: "lthr", min: 100, max: 220 },
  "s-maxhr": { key: "max_hr", min: 140, max: 220 },
  "s-age": { key: "age", min: 10, max: 100 },
  "s-cp": { key: "cp", min: 100, max: 500 },
  "s-wprime": { key: "wprime_j", min: 5000, max: 40000 },
  "s-hours": { key: "hours_per_week", min: 1, max: 40 },
}
export const VALIDATED = Object.keys(BOUNDS) as FieldId[]

export function bounds(id: FieldId, limits: Record<string, [number, number] | undefined>) {
  const b = BOUNDS[id]!
  const lim = limits[b.key]
  return { min: lim?.[0] ?? b.min, max: lim?.[1] ?? b.max }
}

export function fieldError(
  id: FieldId,
  values: Record<FieldId, string>,
  limits: Record<string, [number, number] | undefined>,
): string {
  if (!BOUNDS[id]) return ""
  const raw = values[id].trim()
  if (raw === "") return ""
  const v = parseFloat(raw)
  if (isNaN(v)) return "Enter a number"
  const { min, max } = bounds(id, limits)
  if (v < min || v > max) return `Must be between ${min} and ${max}`
  if (id === "s-lthr" || id === "s-maxhr") {
    const l = parseFloat(values["s-lthr"])
    const m = parseFloat(values["s-maxhr"])
    if (!isNaN(l) && !isNaN(m) && l >= m) {
      return id === "s-lthr" ? `LTHR (${l}) must be below max HR (${m})` : `Max HR (${m}) must be above LTHR (${l})`
    }
  }
  return ""
}

export const allValid = (values: WizardState["values"], limits: Record<string, [number, number] | undefined>) =>
  VALIDATED.every((id) => !fieldError(id, values, limits))

// Untouched fields are omitted from the save payload.
export function buildPayload(s: WizardState): Record<string, unknown> {
  const t = new Set(s.touched)
  const out: Record<string, unknown> = {}
  const num = (id: FieldId, name: string, parse: (x: string) => number) => {
    const v = parse(s.values[id])
    if (t.has(id) && !isNaN(v)) out[name] = v
  }
  num("s-weight", "weight", parseFloat)
  num("s-ftp", "ftp", parseFloat)
  num("s-lthr", "lthr", parseFloat)
  num("s-maxhr", "max_hr", parseFloat)
  if ("lthr" in out && s.icuOrigin.includes("s-lthr")) out.lthr_source_hint = "icu"
  if (s.targetModeTouched) out.target_mode = s.targetMode
  num("s-age", "age", (x) => parseInt(x, 10))
  num("s-cp", "cp", (x) => parseInt(x, 10))
  num("s-wprime", "wprime_j", (x) => parseInt(x, 10))
  if (t.has("s-sex")) out.sex = s.values["s-sex"]
  const wd = s.values["s-workout-dir"].trim()
  if (t.has("s-workout-dir") && wd) out.workout_dir = wd
  num("s-hours", "hours_per_week", parseFloat)
  if (s.daysTouched) out.available_days = s.days.map(Number).sort((a, b) => a - b)
  if (s.restTouched) out.rest_days = s.rest.map(Number).sort((a, b) => a - b)
  return out
}

// A day cannot be both a training day and a rest day: choosing one clears the other.
export function toggleDay(s: WizardState, day: string): WizardState {
  const on = !s.days.includes(day)
  const clearsRest = on && s.rest.includes(day)
  return {
    ...s,
    days: on ? [...s.days, day] : s.days.filter((d) => d !== day),
    rest: clearsRest ? s.rest.filter((d) => d !== day) : s.rest,
    daysTouched: true,
    restTouched: s.restTouched || clearsRest,
  }
}
export function toggleRest(s: WizardState, day: string): WizardState {
  const on = !s.rest.includes(day)
  const clearsDay = on && s.days.includes(day)
  return {
    ...s,
    rest: on ? [...s.rest, day] : s.rest.filter((d) => d !== day),
    days: clearsDay ? s.days.filter((d) => d !== day) : s.days,
    restTouched: true,
    daysTouched: s.daysTouched || clearsDay,
  }
}

export const LS_KEY = "shepherd_setup"
export function serialize(s: WizardState) {
  return { ...s.values, days: s.days, rest: s.rest, touched: s.touched, icuOrigin: s.icuOrigin,
    daysTouched: s.daysTouched, restTouched: s.restTouched, targetMode: s.targetMode,
    targetModeTouched: s.targetModeTouched }
}
export function restore(base: WizardState, o: Record<string, unknown> | null): WizardState {
  if (!o) return base
  const values = { ...base.values }
  for (const id of FIELD_IDS) if (typeof o[id] === "string" && o[id] !== "") values[id] = o[id] as string
  const strs = (x: unknown, fallback: string[]) => (Array.isArray(x) ? (x as string[]) : fallback)
  const mode = o.targetMode === "hr" || o.targetMode === "power" ? o.targetMode : base.targetMode
  return {
    values,
    touched: strs(o.touched, base.touched) as FieldId[],
    icuOrigin: strs(o.icuOrigin, base.icuOrigin) as FieldId[],
    days: strs(o.days, base.days),
    rest: strs(o.rest, base.rest),
    daysTouched: !!o.daysTouched,
    restTouched: !!o.restTouched,
    targetMode: mode,
    targetModeTouched: o.targetMode === "hr" || o.targetMode === "power" ? !!o.targetModeTouched : base.targetModeTouched,
  }
}

export interface SetupDefaults { workout_dir?: string; weight?: number; ftp?: number; lthr?: number; max_hr?: number }
export const getDefaults = (signal?: AbortSignal) => api<SetupDefaults>("/api/setup/defaults", { signal })
export const getAthleteNumbers = () =>
  api<AthleteNumbers>("/api/icu/athlete-numbers")
export const checkActivities = () =>
  api<ActivitiesCheck>(
    "/api/setup/check-activities", { method: "POST", json: { use_connection: true } })
export const pickFolder = () => api<PickedFolder>("/api/setup/pick-folder")
// 409 = a profile already exists and the picker must choose; any other non-ok is a failure.
export async function ensureProfile(): Promise<true | number> {
  try {
    const r = await fetch("/api/setup/ensure-profile", { method: "POST" })
    return r.ok ? true : r.status
  } catch {
    return 0
  }
}
