import { useState } from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { cancelRestore, getStagedRestore, stageRestore } from "@/lib/backup"
import { useLoad } from "@/screens/panel"

const FILES = [
  { href: "/api/export/activities.csv", label: "Activities (CSV)" },
  { href: "/api/export/wellness.csv", label: "Wellness: fitness, HRV, sleep (CSV)" },
  { href: "/api/export/checkins.csv", label: "Daily check-ins (CSV)" },
  { href: "/api/export/backup", label: "Full backup (.tar.gz)" },
]

/** Open-file downloads of the rider's data, and restoring a backup (applied at the next start). */
export function YourData() {
  const [staged, , refresh] = useLoad(getStagedRestore)
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")

  const run = async (work: () => Promise<unknown>) => {
    setBusy(true)
    setError("")
    try {
      await work()
      setFile(null)
      refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <CardContent className="space-y-3 p-4 text-sm">
        <h2 className="text-sm font-semibold">Your data</h2>
        <p className="text-muted-foreground">CSV files open in any spreadsheet. The full backup holds every profile, plan, ride file and database.</p>
        <ul className="list-disc space-y-1 pl-5">
          {FILES.map((f) => (
            <li key={f.href}><a className="underline" href={f.href} download>{f.label}</a></li>
          ))}
        </ul>
        <p className="text-muted-foreground">
          The backup leaves out your intervals.icu and AI keys. A restore keeps the ones you have now, so you only enter them again on a new install.
        </p>
        <div className="space-y-2 border-t pt-3">
          <h3 className="font-semibold">Restore a backup</h3>
          <p className="text-muted-foreground">
            Choose a backup file. It is checked now and replaces everything you have the next time Shepherd starts, so restart it afterwards (in Docker, restart the container).
          </p>
          <div className="flex flex-wrap items-end gap-2">
            <Label className="flex-col items-start gap-1">
              Backup file (.tar.gz)
              <Input type="file" accept=".gz,.tgz,application/gzip" className="w-64" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            </Label>
            <Button size="sm" variant="outline" disabled={busy || !file} onClick={() => run(() => stageRestore(file!))}>
              Check and stage
            </Button>
          </div>
          {staged.state === "ok" && staged.data.pending && (
            <div className="space-y-2" role="status">
              <p>
                A backup from {staged.data.created_at || "an unknown date"} ({staged.data.files} files) will replace your data when Shepherd restarts.
              </p>
              <Button size="sm" variant="ghost" disabled={busy} onClick={() => run(cancelRestore)}>Cancel restore</Button>
            </div>
          )}
          {error && <p role="alert">Couldn’t do that: {error}</p>}
        </div>
      </CardContent>
    </Card>
  )
}
