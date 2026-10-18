import type { Balance, BalanceBucket, BalanceTargets } from "@/api/types"
import { api } from "@/lib/api"

export const SPORTS = ["cycling", "running", "swimming", "other"] as const
export type Sport = (typeof SPORTS)[number]
export const NAME: Record<Sport, string> = { cycling: "Cycling", running: "Running", swimming: "Swimming", other: "Other" }
export const LIMITERS: Sport[] = ["cycling", "running", "swimming"]

export const getBalance = (weeks = 12) => api<Balance>(`/api/balance?weeks=${weeks}`)
export const saveBalanceTargets = (targets: Record<string, number> | null, limiter: string | null) =>
  api<BalanceTargets>("/api/balance/targets", { method: "PUT", json: { targets, limiter } })

export const hours = (v: number) => `${Math.round(v * 10) / 10} h`

/** The chart's text alternative: the period, the average week and where the hours went. */
export function summarise(weeks: BalanceBucket[]): string {
  const total = weeks.reduce((a, w) => a + w.total_hours, 0)
  if (!weeks.length || total === 0) return "No training hours in this period."
  const by = SPORTS.map((s) => [s, weeks.reduce((a, w) => a + w.hours[s], 0)] as const).filter(([, v]) => v > 0)
  const parts = by.map(([s, v]) => `${NAME[s].toLowerCase()} ${Math.round((100 * v) / total)}%`).join(", ")
  const peak = weeks.reduce((a, w) => (w.total_hours > a.total_hours ? w : a))
  return `${weeks.length} weeks from ${weeks[0].start} to ${weeks[weeks.length - 1].end}: ${hours(total)} in all, ${hours(total / weeks.length)} a week on average (${parts}). Biggest week ${hours(peak.total_hours)}, the week of ${peak.start}.`
}

/** The typed percents as a target split: null when every box is empty, an error when they do not add up to 100. */
export function parseTargets(text: Record<string, string>): { targets: Record<string, number> | null; error: string } {
  const filled = SPORTS.filter((s) => (text[s] ?? "").trim() !== "")
  if (!filled.length) return { targets: null, error: "" }
  const targets: Record<string, number> = {}
  for (const s of SPORTS) {
    const raw = (text[s] ?? "").trim()
    const v = raw === "" ? 0 : Number(raw)
    if (!Number.isFinite(v) || v < 0 || v > 100) return { targets: null, error: `${NAME[s]} must be a percent from 0 to 100.` }
    targets[s] = v
  }
  const sum = SPORTS.reduce((a, s) => a + targets[s], 0)
  if (Math.abs(sum - 100) > 0.05) return { targets: null, error: `The targets add up to ${Math.round(sum * 10) / 10}, they need to add up to 100.` }
  return { targets, error: "" }
}
