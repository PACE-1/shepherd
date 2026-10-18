import type { OpenWaterNote, OpenWaterNotes, SwimActivities, SwimCss, SwimCssTest } from "@/api/types"
import { api } from "@/lib/api"
import type { Trial } from "@/lib/run"
import { formatClock } from "@/lib/sports"

export const getSwimCss = () => api<SwimCss>("/api/swim/css")
export const getSwimActivities = () => api<SwimActivities>("/api/swim/activities")
export const cssTest = (trials: Trial[], save = false) =>
  api<SwimCssTest>("/api/swim/css-test", { method: "POST", json: { trials, save } })

export type NoteFields = Omit<OpenWaterNote, "id">
export const getOpenWaterNotes = () => api<OpenWaterNotes>("/api/swim/open-water")
const note = (id: string) => `/api/swim/open-water/${encodeURIComponent(id)}`
export const addOpenWaterNote = (n: NoteFields) => api<OpenWaterNote>("/api/swim/open-water", { method: "POST", json: n })
export const editOpenWaterNote = (id: string, n: NoteFields) => api<OpenWaterNote>(note(id), { method: "PUT", json: n })
export const deleteOpenWaterNote = (id: string) => api<{ ok: boolean }>(note(id), { method: "DELETE" })

/** Seconds per 100 m as "1:35 /100 m". */
export const per100 = (s: number) => `${formatClock(s)} /100 m`

/** Where a swim was: "Pool 25 m", "Open water", or "–" when intervals.icu did not say. */
export function waterLabel(water: string | undefined, poolLength: number | null | undefined): string {
  if (water === "open_water") return "Open water"
  if (water === "pool") return poolLength ? `Pool ${Math.round(poolLength * 10) / 10} m` : "Pool"
  return "–"
}

/** "16.5" -> 16.5, "" -> null; undefined when it is not a number. */
export function parseTemp(text: string): number | null | undefined {
  const t = text.trim()
  if (!t) return null
  return /^-?\d+([.,]\d+)?$/.test(t) ? Number(t.replace(",", ".")) : undefined
}
