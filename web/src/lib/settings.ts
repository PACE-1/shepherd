import type { BackfillHistoryStarted, BackfillHistoryStatus, DiagErrors, DiagHealth, GarminStatus, GarminSynced, IcuPushResult, IcuPushStatus, LogTail, SettingsRead, SettingsSaved, SyncStatus, UpdateCheck, VersionInfo, WorkoutFolders, ZonesSaved } from "@/api/types"
import { api } from "@/lib/api"

export const getSettings = () => api<SettingsRead>("/api/settings")
export const getSyncStatus = () => api<SyncStatus>("/api/sync/status")
export const getVersion = () => api<VersionInfo>("/api/version")
export const checkUpdate = (force: boolean) => api<UpdateCheck>(`/api/update/check?force=${force ? 1 : 0}`)
export const syncNow = () => api<Record<string, unknown>>("/api/sync", { method: "POST" })

/** Saves only what changed. The server rejects values outside its limits with a message. */
export const saveSettings = (changes: Record<string, number | string>) =>
  api<SettingsSaved>("/api/settings", { method: "POST", json: changes })

export interface RiderForm {
  weight: string
  ftp: string
  lthr: string
  maxHr: string
  targetMode: "power" | "hr"
}

export const formFrom = (s: SettingsRead): RiderForm => ({
  weight: String(s.weight),
  ftp: String(s.ftp),
  lthr: String(s.lthr),
  maxHr: String(s.max_hr),
  targetMode: s.target_mode === "hr" ? "hr" : "power",
})

type Limits = Partial<Record<"ftp" | "weight" | "lthr" | "max_hr", [number, number]>>

/** What to send (only changed fields) and what is wrong with the form, if anything. */
export function diff(s: SettingsRead, f: RiderForm, limits: Limits = {}) {
  const changes: Record<string, number | string> = {}
  const problems: string[] = []
  const nums: [keyof Limits, string, string, number][] = [
    ["weight", "Weight", f.weight, s.weight],
    ["ftp", "FTP", f.ftp, s.ftp],
    ["lthr", "LTHR", f.lthr, s.lthr],
    ["max_hr", "Max HR", f.maxHr, s.max_hr],
  ]
  for (const [key, label, raw, old] of nums) {
    const v = Number(raw)
    if (raw.trim() === "" || !Number.isFinite(v)) { problems.push(`${label} must be a number.`); continue }
    const [lo, hi] = limits[key] ?? [0, Infinity]
    if (v < lo || v > hi) { problems.push(`${label} must be between ${lo} and ${hi}.`); continue }
    if (v !== old) changes[key] = v
  }
  if (!problems.length && Number(f.maxHr) <= Number(f.lthr)) problems.push("Max HR must be above LTHR.")
  if (f.targetMode !== (s.target_mode === "hr" ? "hr" : "power")) changes.target_mode = f.targetMode
  return { changes, problems }
}

// ── intervals.icu connection and calendar push ─────────────────────────────

/** Signs in through intervals.icu and returns to Settings. */
export const connectUrl = `/oauth/icu/start?return_to=${encodeURIComponent("/v2/?wizard=settings")}`
export const disconnectIcu = () => api<{ ok: boolean }>("/api/icu/disconnect", { method: "POST" })
export const getGarmin = () => api<GarminStatus>("/api/garmin")
export const garminLogin = (email: string, password: string) =>
  api<GarminStatus>("/api/garmin/login", { method: "POST", json: { email: email.trim(), password } })
export const garminMfa = (code: string) => api<GarminStatus>("/api/garmin/mfa", { method: "POST", json: { code: code.trim() } })
export const garminSync = () => api<GarminSynced>("/api/garmin/sync", { method: "POST" })
export const garminRelay = (on: boolean) => api<GarminStatus>("/api/garmin/settings", { method: "POST", json: { relay_to_icu: on } })
export const garminDisconnect = () => api<GarminStatus>("/api/garmin", { method: "DELETE" })
export const getPush = () => api<IcuPushStatus>("/api/icu/push")
/** `sync` turns the keep-in-sync switch on or off. */
export const setPushSync = (sync: boolean) => api<IcuPushResult>("/api/icu/push", { method: "POST", json: { sync } })
export const pushNow = () => api<IcuPushResult>("/api/icu/push", { method: "POST", json: {} })

// ── workout folders ───────────────────────────────────────────────────────
export const getFolders = () => api<WorkoutFolders>("/api/settings/workout-folders")
/** An empty path clears the extra folder. */
export const setExtraFolder = (extraDir: string) => api<WorkoutFolders>("/api/settings/workout-folders", { method: "POST", json: { extra_dir: extraDir } })

// ── custom zones ──────────────────────────────────────────────────────────
export interface ZoneRow {
  zone: string
  name: string
  low: number
  high: number
}
/** `null` resets the kind to the automatic zones. */
export const saveZones = (kind: "power" | "hr", zones: ZoneRow[] | null) => api<ZonesSaved>("/api/settings/zones", { method: "POST", json: { kind, zones } })

/** What is wrong with the rows, or "". The server enforces 0 ≤ low < high ≤ 3000 for each zone. */
export function zoneProblem(rows: { low: string; high: string }[]): string {
  for (let i = 0; i < rows.length; i++) {
    const lo = Number(rows[i].low)
    const hi = Number(rows[i].high)
    if (rows[i].low === "" || rows[i].high === "" || !Number.isFinite(lo) || !Number.isFinite(hi)) return `Zone ${i + 1}: enter both numbers.`
    if (!(lo >= 0 && lo < hi && hi <= 3000)) return `Zone ${i + 1}: the low number must be below the high number, and both between 0 and 3000.`
  }
  return ""
}

// ── logs and health ───────────────────────────────────────────────────────
export const getLogs = (lines: number) => api<LogTail>(`/api/logs?lines=${lines}`)
export const getErrors = () => api<DiagErrors>("/api/diag/recent-errors?limit=30")
export const getHealth = () => api<DiagHealth>("/api/diag/health")

// ── power history backfill ────────────────────────────────────────────────
export const startHistory = () => api<BackfillHistoryStarted>("/api/profile/backfill-history", { method: "POST" })
export const historyStatus = (id: string) => api<BackfillHistoryStatus>(`/api/profile/backfill-history/status?task_id=${encodeURIComponent(id)}`)
