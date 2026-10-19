import type { RacePredictor } from "@/api/types"
import { api } from "@/lib/api"

export type RaceTarget = { race: string; time_s: number }

export const getRacePredictor = (target?: RaceTarget) =>
  api<RacePredictor>(target ? `/api/run/predict?target_race=${encodeURIComponent(target.race)}&target_time_s=${target.time_s}` : "/api/run/predict")

/** "19:50" or "1:46:39" -> seconds; null when it is neither or not above zero. */
export function parseRaceTime(text: string): number | null {
  const m = /^\s*(?:(\d+):)?(\d+):([0-5]\d)\s*$/.exec(text)
  if (!m) return null
  const s = Number(m[1] ?? 0) * 3600 + Number(m[2]) * 60 + Number(m[3])
  return s > 0 ? s : null
}

/** 1190 -> "19:50"; 11509 -> "3:11:49". */
export function raceTime(s: number): string {
  const t = Math.round(s)
  const h = Math.floor(t / 3600)
  const m = Math.floor((t % 3600) / 60)
  const sec = String(t % 60).padStart(2, "0")
  return h ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`
}
