import type { GenerateRequest, GoalType, RaceEvent } from "@/lib/home"

export const GOALS: [GoalType, string][] = [
  ["general", "General fitness"],
  ["ftp", "Raise FTP"],
  ["vo2max", "Raise VO2max"],
  ["ftp_vo2max", "FTP and VO2max together"],
  ["ctl", "Build fitness (CTL)"],
  ["event", "Prepare for an event"],
  ["continuous", "Keep training, no end date"],
]

export interface Advanced {
  distribution: "polarized" | "pyramidal" | "threshold"
  mode: "auto" | "fixed_core" | "template"
  template: "polarized_base" | "ftp_builder" | "custom"
  bands: { tempo_ss: string; threshold: string; vo2: string; sprint: string }
  block: boolean
  vo2Micro: boolean
  focus: "both" | "ftp" | "vo2"
  backdate: boolean
  startDate: string
  recognized: boolean // the start date came from a ride scan
  dayHours: string[] // Monday first; empty strings mean "not set"
  useDayHours: boolean
  eventKm: string
  eventClimb: string
  eventType: string
  endDate: string // non-event goals
  races: { date: string; name: string; priority: "B" | "C" }[]
  phaseWeeks: Record<string, string> | null // edited split, by phase name
}

export const NO_ADVANCED: Advanced = {
  distribution: "polarized", mode: "auto", template: "polarized_base",
  bands: { tempo_ss: "", threshold: "", vo2: "", sprint: "" },
  block: false, vo2Micro: false, focus: "both", backdate: false, startDate: "", recognized: false,
  dayHours: ["", "", "", "", "", "", ""], useDayHours: false,
  eventKm: "", eventClimb: "", eventType: "granfondo", endDate: "", races: [], phaseWeeks: null,
}

const num = (v: string) => (v.trim() === "" ? undefined : Number(v))

/** What is wrong with the advanced options, or "". */
export function advancedProblem(a: Advanced, goal: GoalType, today: string): string {
  if (a.mode === "template" && a.template === "custom") {
    const vals = Object.values(a.bands).map((v) => Number(v || 0))
    if (vals.some((v) => !(v >= 0 && v <= 100))) return "Each custom intensity share must be between 0 and 100."
    if (vals.reduce((n, v) => n + v, 0) > 100) return "The custom intensity shares add up to more than 100."
  }
  if (a.backdate && (!a.startDate || a.startDate > today)) return "Pick a start date that is today or earlier."
  if (a.useDayHours && a.dayHours.some((h) => h !== "" && !(Number(h) >= 0 && Number(h) <= 12))) return "Hours for a day must be between 0 and 12."
  if (a.useDayHours && a.dayHours.every((h) => !(Number(h) > 0))) return "Give at least one day some hours."
  for (const r of a.races) if (!r.date || r.date <= today) return "Each extra race needs a date in the future."
  if (a.endDate && a.endDate <= today) return "The end date must be in the future."
  if (a.phaseWeeks && Object.values(a.phaseWeeks).some((v) => !(Number(v) >= 1 && Number(v) <= 30))) return "Each phase needs between 1 and 30 weeks."
  if (goal === "event" && a.eventKm !== "" && !(Number(a.eventKm) > 0)) return "Event distance must be above 0."
  return ""
}

/** Adds only what differs from the defaults, so an untouched form sends what it always sent. */
export function applyAdvanced(base: GenerateRequest, a: Advanced, recommended: Record<string, number> | null): GenerateRequest {
  const r: GenerateRequest = { ...base }
  if (a.distribution !== "polarized") r.distribution = a.distribution
  if (a.mode !== "auto") r.plan_mode = a.mode
  if (a.mode === "template") {
    r.template_id = a.template
    if (a.template === "custom") r.custom_bands = { tempo_ss: Number(a.bands.tempo_ss || 0), threshold: Number(a.bands.threshold || 0), vo2: Number(a.bands.vo2 || 0), sprint: Number(a.bands.sprint || 0) }
  }
  if (a.block) r.block_periodization = true
  if (a.vo2Micro) r.vo2_microintervals_only = true
  if (base.goal === "continuous") r.focus = a.focus
  if (a.backdate && a.startDate) {
    r.start_date = a.startDate
    r.entry_mode = a.recognized ? "recognized" : "declared"
  }
  if (a.useDayHours) {
    const hours = a.dayHours.map((h) => Number(h || 0))
    r.daily_availability = Object.fromEntries(hours.map((h, i) => [i, h]))
    r.hours_per_week = Math.round(hours.reduce((n, v) => n + v, 0) * 10) / 10
    r.max_weekday = Math.max(...hours.slice(0, 5), 0.5)
    r.max_weekend = Math.max(hours[5], hours[6], 0.5)
    r.rest_days = hours.flatMap((h, i) => (h > 0 ? [] : [i]))
  }
  if (base.goal === "event") {
    const km = num(a.eventKm)
    const climb = num(a.eventClimb)
    if (km) r.event_km = km
    if (climb) r.event_climb = climb
    if (a.eventType !== "granfondo" || km || climb) r.event_type = a.eventType
  } else if (a.endDate && base.goal !== "general" && base.goal !== "continuous") {
    r.event_date = a.endDate
  }
  const bc: RaceEvent[] = a.races.map((x) => ({ date: x.date, priority: x.priority, name: x.name }))
  // The A race travels in the goal fields (event_*); the server refuses an A inside events.
  if (bc.length && base.goal !== "continuous") r.events = bc
  if (a.phaseWeeks && recommended) {
    const edited = Object.fromEntries(Object.entries(a.phaseWeeks).map(([k, v]) => [k, Number(v)]))
    const same = Object.keys({ ...recommended, ...edited }).every((k) => (recommended[k] ?? 0) === (edited[k] ?? 0))
    if (!same) r.phase_weeks = edited
  }
  return r
}
