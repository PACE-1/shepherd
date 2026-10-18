import type { GearItem, GearOverview } from "@/api/types"
import { api } from "@/lib/api"

export type GearKind = "bike" | "shoes" | "component"

export interface GearForm {
  name: string
  kind: GearKind
  parent_id: string
  started_on: string
  service_every_km: string
  service_every_hours: string
  icu_name: string
}

export const emptyForm = (): GearForm => ({
  name: "",
  kind: "bike",
  parent_id: "",
  started_on: "",
  service_every_km: "",
  service_every_hours: "",
  icu_name: "",
})

export const formOf = (i: GearItem): GearForm => ({
  name: i.name,
  kind: i.kind as GearKind,
  parent_id: i.parent_id ?? "",
  started_on: i.started_on ?? "",
  service_every_km: i.service_every_km == null ? "" : String(i.service_every_km),
  service_every_hours: i.service_every_hours == null ? "" : String(i.service_every_hours),
  icu_name: i.icu_name ?? "",
})

/** Why the form can't be saved, or "". Thresholds are optional and never defaulted. */
export function formProblem(f: GearForm): string {
  if (!f.name.trim()) return "Give it a name."
  for (const [label, v] of [["Service every (km)", f.service_every_km], ["Service every (hours)", f.service_every_hours]] as const) {
    if (v.trim() !== "" && !(Number(v) > 0)) return `${label} must be a number above 0, or empty.`
  }
  return ""
}

export const bodyOf = (f: GearForm) => ({
  name: f.name.trim(),
  kind: f.kind,
  parent_id: f.kind === "component" ? f.parent_id || null : null,
  started_on: f.started_on || null,
  service_every_km: f.service_every_km.trim() === "" ? null : Number(f.service_every_km),
  service_every_hours: f.service_every_hours.trim() === "" ? null : Number(f.service_every_hours),
  icu_name: f.kind === "component" ? null : f.icu_name.trim() || null,
})

export const getGear = () => api<GearOverview>("/api/gear")
export const addGear = (f: GearForm) => api<GearOverview>("/api/gear", { method: "POST", json: bodyOf(f) })
export const editGear = (id: string, f: GearForm) => api<GearOverview>(`/api/gear/${encodeURIComponent(id)}`, { method: "PATCH", json: bodyOf(f) })
export const retireGear = (id: string, retired: boolean) => api<GearOverview>(`/api/gear/${encodeURIComponent(id)}`, { method: "PATCH", json: { retired } })
export const deleteGear = (id: string) => api<GearOverview>(`/api/gear/${encodeURIComponent(id)}`, { method: "DELETE" })
export const serviceDone = (id: string, date: string) =>
  api<GearOverview>(`/api/gear/${encodeURIComponent(id)}/service`, { method: "POST", json: date ? { date } : {} })
/** `gear_id`: an item id, "none" for no gear, null for the automatic choice. */
export const assignRide = (activity_id: string, gear_id: string | null) =>
  api<GearOverview>("/api/gear/assignment", { method: "PUT", json: { activity_id, gear_id } })

export const STATE_TEXT: Record<string, string> = {
  ok: "OK",
  due_soon: "Due soon",
  due: "Due",
  no_threshold: "No threshold set",
  retired: "Retired",
}

/** "412 / 1000 km (41%)", or just "412 km" when the rider set no threshold. */
export function progress(used: number, cap: number | null | undefined, unit: string, pct: number | null | undefined): string {
  const n = Math.round(used * 10) / 10
  return cap ? `${n} / ${cap} ${unit} (${Math.round((pct ?? 0) * 100)}%)` : `${n} ${unit}`
}

export const needsAttention = (items: GearItem[]) => items.filter((i) => i.state === "due" || i.state === "due_soon")
