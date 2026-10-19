import type { BackupStaged } from "@/api/types"
import { api } from "@/lib/api"

export const getStagedRestore = () => api<BackupStaged>("/api/import/backup")
export const stageRestore = (file: File) => {
  const form = new FormData()
  form.append("file", file)
  return api<BackupStaged>("/api/import/backup", { method: "POST", form })
}
export const cancelRestore = () => api<BackupStaged>("/api/import/backup", { method: "DELETE" })
