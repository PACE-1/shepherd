import type { Race, RaceDayPlan, RacesStatus } from "@/api/types"
import { api } from "@/lib/api"
import { regeneratePlan } from "@/lib/home"

export type Priority = "A" | "B" | "C"
export const EVENT_TYPES: [string, string][] = [
  ["granfondo", "Gran fondo"],
  ["sportive", "Sportive"],
  ["century", "Century"],
  ["crit", "Criterium / short race"],
  ["ultra", "Ultra"],
]
export const DISCIPLINES: [string, string][] = [
  ["cycling", "Cycling"],
  ["triathlon", "Triathlon"],
  ["running", "Running"],
  ["swimming", "Swimming"],
]
// Labels only: no distance-specific plan is built (src/races.py).
export const TRI_DISTANCES: [string, string][] = [
  ["sprint", "Sprint"],
  ["olympic", "Olympic"],
  ["70.3", "70.3"],
  ["ironman", "Ironman"],
  ["custom", "Custom"],
]
export const LABEL_NOTE =
  "Triathlon, run and swim races are labels: the plan toward one uses your own hours and sport split, the cycling plan's taper and your run, swim and strength sessions, which taper too. No distance-specific triathlon plan is built, and the race-day plan is cycling-only."
export const isCycling = (discipline: string | null | undefined) => (discipline ?? "cycling") === "cycling"
const DISC_LABEL = Object.fromEntries(DISCIPLINES)
/** "Triathlon (70.3)", "Running", "" for a cycling race. */
export const disciplineText = (r: Pick<Race, "discipline" | "distance">) =>
  isCycling(r.discipline) ? "" : `${DISC_LABEL[r.discipline ?? ""] ?? r.discipline}${r.distance ? ` (${r.distance})` : ""}`

export const PRIORITY_TEXT: Record<Priority, string> = {
  A: "A: the race the plan builds toward (full taper)",
  B: "B: matters (smaller taper)",
  C: "C: train through (easy day before)",
}

/** The editable fields of a race, as the form holds them (strings, "" for not set). */
export interface RaceForm {
  name: string
  date: string
  priority: Priority
  discipline: string
  distance: string
  event_type: string
  event_km: string
  event_climb_m: string
  expected_duration_h: string
  start_time: string
  arrive_time: string
}

export const emptyForm = (): RaceForm => ({
  name: "",
  date: "",
  priority: "B",
  discipline: "cycling",
  distance: "",
  event_type: "granfondo",
  event_km: "",
  event_climb_m: "",
  expected_duration_h: "",
  start_time: "",
  arrive_time: "",
})

export const formOf = (r: Race): RaceForm => ({
  name: r.name ?? "",
  date: r.date,
  priority: r.priority as Priority,
  discipline: r.discipline ?? "cycling",
  distance: r.distance ?? "",
  event_type: r.event_type ?? "granfondo",
  event_km: r.event_km ? String(r.event_km) : "",
  event_climb_m: r.event_climb_m ? String(r.event_climb_m) : "",
  expected_duration_h: r.expected_duration_h ? String(r.expected_duration_h) : "",
  start_time: r.start_time ?? "",
  arrive_time: r.arrive_time ?? "",
})

/** The request body for a form: numbers as numbers, empty fields as null. */
export function bodyOf(f: RaceForm) {
  const num = (s: string) => (s.trim() === "" ? null : Number(s))
  return {
    name: f.name.trim(),
    date: f.date,
    priority: f.priority,
    discipline: f.discipline,
    distance: f.discipline === "triathlon" ? f.distance || null : null,
    event_type: f.event_type,
    event_km: num(f.event_km) ?? 0,
    event_climb_m: num(f.event_climb_m) ?? 0,
    expected_duration_h: num(f.expected_duration_h),
    start_time: f.start_time || null,
    arrive_time: f.arrive_time || null,
  }
}

/** Why the form can't be saved, or "" when it can. `isNew`: a new race can't be in the past. */
export function raceProblem(f: RaceForm, today: string, isNew: boolean): string {
  if (!f.date) return "Pick the race date."
  if (isNew && f.date < today) return "The race can't be in the past."
  if (f.discipline === "triathlon" && !f.distance) return "Pick the triathlon distance."
  for (const [v, what] of [[f.event_km, "Distance"], [f.event_climb_m, "Climbing"], [f.expected_duration_h, "Expected duration"]] as const) {
    if (v.trim() !== "" && !(Number(v) >= 0)) return `${what} must be a number, 0 or more.`
  }
  if (f.start_time && f.arrive_time && f.arrive_time > f.start_time) return "Arrival can't be after the start."
  return ""
}

export const getRaces = () => api<RacesStatus>("/api/races")
const one = (id: string) => `/api/races/${encodeURIComponent(id)}`
export const createRace = (f: RaceForm) => api<RacesStatus>("/api/races", { method: "POST", json: bodyOf(f) })
export const saveRace = (id: string, f: RaceForm) => api<RacesStatus>(one(id), { method: "PUT", json: bodyOf(f) })
export const removeRace = (id: string) => api<RacesStatus>(one(id), { method: "DELETE" })
export const syncRaces = () => api<RacesStatus>("/api/races/sync", { method: "POST", json: {} })
export const getRaceDay = (id: string) => api<RaceDayPlan>(`${one(id)}/race-day`)

/** Rebuilds the plan when the change reached it, as the Plan's Time off form does. Returns an error message, or "". */
export async function rebuildIfNeeded(s: RacesStatus): Promise<string> {
  if (!s.plan_synced) return ""
  try {
    await regeneratePlan()
    return ""
  } catch (e) {
    return `Saved, but rebuilding the plan failed: ${e instanceof Error ? e.message : String(e)}. Rebuild it from the Plan tab.`
  }
}

export const countdown = (days: number) =>
  days > 1 ? `${days} days to go` : days === 1 ? "tomorrow" : days === 0 ? "today" : `${-days} days ago`

export const fmtHours = (h: number) => {
  const m = Math.round(h * 60)
  return `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")} min`
}
