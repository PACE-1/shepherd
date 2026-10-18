import type { Readiness, SportsLoad } from "@/api/types"

// /api/readiness also carries the sleep and training blocks (the model allows extra fields), but its schema does not name them.
type Block = Record<string, number | string | null | undefined>
type WithInputs = { sleep?: Block; training?: Block; readiness?: { components?: Record<string, number> } | null }

const signed = (v: number) => `${v > 0 ? "+" : ""}${Math.round(v * 10) / 10}`

const HRV: Record<string, string> = {
  GREEN: "your 7-day HRV is above your baseline range",
  ORANGE: "your 7-day HRV is within your baseline range",
  RED: "your 7-day HRV is below your baseline range",
}

const FORM_SOURCE: Record<string, string> = {
  icu: "from intervals.icu, all sports",
  icu_cached: "from intervals.icu, last stored value, all sports",
  local: "from your imported rides",
}

/** One plain line naming the inputs that went into today's readiness score (only those that did). */
export function readinessDrivers(r: Readiness): string {
  const { sleep = {}, training = {}, readiness } = r as Readiness & WithInputs
  const used = readiness?.components ?? {}
  const parts: string[] = []
  if ("hrv" in used) parts.push(HRV[String(sleep.hrv_status)] ?? "your 7-day HRV (no baseline range yet)")
  if ("rhr" in used && typeof sleep.rhr_delta === "number") parts.push(`resting heart rate ${signed(sleep.rhr_delta)} bpm against your 7-day average`)
  if ("sleep" in used && typeof sleep.sleep_h === "number") parts.push(`${Math.round(sleep.sleep_h * 10) / 10} h of sleep`)
  if ("tsb" in used && typeof training.tsb === "number") {
    const src = FORM_SOURCE[String(training.source)]
    parts.push(`form ${signed(training.tsb)}${src ? ` (${src})` : ""}`)
  }
  if ("subjective" in used) parts.push("your daily check-in")
  return parts.length ? `Today’s score used: ${parts.join("; ")}.` : ""
}

export const SPORT_NAME: Record<string, string> = { cycling: "Cycling", running: "Running", swimming: "Swimming", other: "Other" }

/** Last-7-day training load per sport, biggest first, with the all-sports total. */
export function recentLoadByType(load: SportsLoad) {
  const rows = Object.entries(load.sports)
    .map(([sport, l]) => ({ sport, name: SPORT_NAME[sport] ?? sport, load: l.week_load }))
    .sort((a, b) => b.load - a.load)
  return { rows, total: load.combined.week_load }
}
