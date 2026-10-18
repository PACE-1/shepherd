import type { Fueling, NutritionConnection, NutritionSync, NutritionTest } from "@/api/types"
import { api } from "@/lib/api"

export const getNutrition = () => api<NutritionConnection>("/api/nutrition/connection")
/** An empty key keeps the saved one (for the same address only); the key is never sent back. */
export const saveNutrition = (base_url: string, api_key: string) =>
  api<NutritionConnection>("/api/nutrition/connection", { method: "POST", json: { base_url, api_key } })
export const deleteNutrition = () => api<NutritionConnection>("/api/nutrition/connection", { method: "DELETE" })
export const testNutrition = () => api<NutritionTest>("/api/nutrition/test", { method: "POST" })
export const syncNutrition = () => api<NutritionSync>("/api/nutrition/sync", { method: "POST", json: {} })
export const getFueling = () => api<Fueling>("/api/fueling")

/** "a to b unit", or one number when the range is a single value. */
export const range = (lo: number, hi: number, unit: string) => (lo === hi ? `${lo} ${unit}` : `${lo} to ${hi} ${unit}`)

/** Carbohydrate logged so far today against the day's range, in words. */
export function carbStatus(logged: number | null | undefined, lo: number, hi: number): string {
  if (logged == null) return "No carbohydrate logged yet today."
  const g = Math.round(logged)
  if (g < lo) return `${g} g logged so far: ${lo - g} to ${hi - g} g more reaches the day's range.`
  if (g > hi) return `${g} g logged so far: ${g - hi} g above the day's range.`
  return `${g} g logged so far: within the day's range.`
}
