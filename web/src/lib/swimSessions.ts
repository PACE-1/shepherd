import type { SwimSessions } from "@/api/types"
import { api } from "@/lib/api"

// The swim session library (src/sessions_swim.py): sets written for the rider's saved CSS.
export const getSwimSessions = () => api<SwimSessions>("/api/swim/sessions")

/** The plain-text download of one session (a text file; no FIT is made for swims). */
export const sessionTextUrl = (id: string) => `/api/swim/sessions/${encodeURIComponent(id)}/text`

/** "40-70 min" for a template's range. */
export const rangeLabel = (min: number, max: number) => `${min}-${max} min`
