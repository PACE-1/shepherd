import type { FolderImportScan, FolderImportStarted, FolderImportState } from "@/api/types"
import { api } from "@/lib/api"

export const getFolderImport = () => api<FolderImportState>("/api/folder-import")

/** `folder` "" removes it; omit a field to keep it. The server checks the folder exists and is readable. */
export const saveFolderImport = (change: { folder?: string; recursive?: boolean }) =>
  api<FolderImportState>("/api/folder-import", { method: "PUT", json: change })

export const startFolderScan = () => api<FolderImportStarted>("/api/folder-import/scan", { method: "POST" })

/** One line for the last scan: what came in, what was skipped, what failed. */
export function scanSummary(s: FolderImportScan): string {
  if (s.error) return s.error
  const n = (k: number, one: string, many = `${one}s`) => `${k} ${k === 1 ? one : many}`
  const parts = [`${n(s.imported ?? 0, "ride")} imported`, `${s.duplicate ?? 0} already in Shepherd`, `${s.failed ?? 0} failed`]
  if (s.remaining) parts.push(`${s.remaining} left for the next scan`)
  return parts.join(", ") + (s.aborted ? " (stopped: the profile changed)" : "") + "."
}
