import type { FtpReviewSaved, FtpTestAnalysis, FtpUpdated, Ok, PrToastQueue, RideDetail, RideImported, RideRpeSaved, RidesSynced } from "@/api/types"
import { api } from "@/lib/api"

export const rideRoute = (id: string) => `#/ride/${encodeURIComponent(id)}`

/** Upload a FIT file. The server refuses oversize (413), unreadable (422) and slow (504) files with a sentence. */
export const importFit = (file: File) => {
  const form = new FormData()
  form.append("fit_file", file)
  return api<RideImported>("/api/ride/import", { method: "POST", form })
}

export const syncRides = (force: boolean) => api<RidesSynced>(`/api/rides/sync?force=${force ? 1 : 0}`, { method: "POST" })

export const getRide = (id: string) => api<RideDetail>(`/api/ride/${encodeURIComponent(id)}/detail?include=samples`)

/** Foster CR-10, 0 to 10; null clears the rating. */
export const setRpe = (id: string, rpe: number | null) =>
  api<RideRpeSaved>(`/api/ride/${encodeURIComponent(id)}/rpe`, { method: "POST", json: { rpe } })

/** Only imported FIT rides can be deleted; the server wants the file's name without the `fit_` prefix. */
export const isFitRide = (id: string) => id.startsWith("fit_")
export const deleteRide = (id: string) => api<Ok>(`/api/rides/${encodeURIComponent(id.replace(/^fit_/, ""))}`, { method: "DELETE" })
export const fitUrl = (id: string) => `/api/rides/${encodeURIComponent(id.replace(/^fit_/, ""))}/fit`

export const getFtpAnalysis = (id: string) => api<FtpTestAnalysis>(`/api/ride/${encodeURIComponent(id)}/ftp-test-analysis`)

export type FtpVerdict = "accepted" | "declined" | "edited"
export const reviewFtp = (id: string, action: FtpVerdict, ftp: number) =>
  api<FtpReviewSaved>(`/api/ride/${encodeURIComponent(id)}/ftp-test-review`, { method: "POST", json: { action, ftp } })

export const updateFtp = (ftp: number, method: string, source: string, applied: boolean) =>
  api<FtpUpdated>("/api/profile/update-ftp", { method: "POST", json: { ftp, method, source, applied } })

/** Rides with a new major personal record since the last look; `drain` clears the queue. */
export const getPrQueue = (drain: boolean) => api<PrToastQueue>(`/api/profile/pr-toast-queue?drain=${drain ? 1 : 0}`)

export const ZONE_NAMES: Record<string, string> = { z1: "Z1 Recovery", z2: "Z2 Endurance", z3: "Z3 Tempo", z4: "Z4 Threshold", z5: "Z5 VO2max", z6: "Z6 Anaerobic", z7: "Z7 Neuromuscular", ss: "Sweet spot" }

/** Race-tagged rides count more when the app fits your own training-load time constants. */
export const setRace = (activityId: string, isRace: boolean) =>
  api<void>(`/api/activity/${encodeURIComponent(activityId)}/race`, { method: "POST", json: { is_race: isRace } })
