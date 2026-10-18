import type { StrengthExercise, StrengthSessions } from "@/api/types"
import { api } from "@/lib/api"

export const getStrengthSessions = (stage?: string) =>
  api<StrengthSessions>(stage ? `/api/strength/sessions?stage=${encodeURIComponent(stage)}` : "/api/strength/sessions")

/** [2, 2] -> "2", [1, 3] -> "1-3". */
export const range = (r: readonly number[] | undefined | null): string =>
  !r || r.length < 2 ? "" : r[0] === r[1] ? String(r[0]) : `${r[0]}-${r[1]}`

/** "1-3 sets of 8-12 repetitions", "2 holds of 30 s", "2 sets of 8-10 repetitions". */
export function prescription(e: StrengthExercise): string {
  const sets = range(e.sets)
  const n = e.sets[1]
  const side = e.per_side ? " each side" : ""
  if (e.hold_s) return `${sets} ${n === 1 ? "hold" : "holds"} of ${e.hold_s} s${side}`
  return `${sets} ${n === 1 ? "set" : "sets"} of ${range(e.reps)} repetitions${side}`
}

/** "180-270 arbitrary units (session-RPE), not comparable with TSS" -- the unit text always travels with the number. */
export const loadText = (au: readonly number[], note: string): string => `${range(au.map(Math.round))} ${note}`
