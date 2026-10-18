import type { InjuryStatus, RampRate } from "@/api/types"
import { api } from "@/lib/api"
import { regeneratePlan } from "@/lib/home"

export type EpisodeType = "injury" | "illness"
export type EpisodeSport = "all" | "cycling" | "running" | "swimming" | "other"

export interface NewEpisode {
  type: EpisodeType
  start: string
  end?: string
  sport: EpisodeSport
  body_area: string
  note: string
}

export const getInjury = () => api<InjuryStatus>("/api/injury")
export const getRampRate = () => api<RampRate>("/api/injury/ramp-rate")

const episode = (id: string) => `/api/injury/episodes/${encodeURIComponent(id)}`
export const addEpisode = (e: NewEpisode) => api<InjuryStatus>("/api/injury/episodes", { method: "POST", json: e })
/** With no `end`, "I'm back": the server ends the episode yesterday. */
export const resolveEpisode = (id: string, end?: string) =>
  api<InjuryStatus>(`${episode(id)}/resolve`, { method: "POST", json: end ? { end } : {} })
export const deleteEpisode = (id: string) => api<InjuryStatus>(episode(id), { method: "DELETE" })

/** Rebuilds the plan when the episode changed its time off. Returns an error message, or "". */
export async function rebuildIfNeeded(s: InjuryStatus): Promise<string> {
  if (!s.plan_synced) return ""
  try {
    await regeneratePlan()
    return ""
  } catch (e) {
    return `Saved, but rebuilding the plan failed: ${e instanceof Error ? e.message : String(e)}. Rebuild it from the Plan tab.`
  }
}

/** Why the form can't be submitted, or "" when it can. */
export function episodeProblem(f: { start: string; end: string }): string {
  if (!f.start) return "Pick the first day."
  if (f.end && f.end < f.start) return "The last day can't be before the first."
  return ""
}

export const LEVEL_TEXT: Record<string, string> = {
  ok: "Within range",
  elevated: "Rising fast",
  high: "Spike",
  no_base: "No recent load to compare with",
}
