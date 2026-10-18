import type { RacePredictor } from "@/api/types"
import { api } from "@/lib/api"

export const getRacePredictor = () => api<RacePredictor>("/api/run/predict")

/** 1190 -> "19:50"; 11509 -> "3:11:49". */
export function raceTime(s: number): string {
  const t = Math.round(s)
  const h = Math.floor(t / 3600)
  const m = Math.floor((t % 3600) / 60)
  const sec = String(t % 60).padStart(2, "0")
  return h ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`
}
