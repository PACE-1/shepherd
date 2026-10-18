import { useEffect, useState } from "react"

import type { FolderImportState } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { getFolderImport, saveFolderImport, scanSummary, startFolderScan } from "@/lib/folderImport"
import { Panel, useLoad } from "@/screens/panel"

const POLL_MS = 1000

/** One folder of .fit files per profile. A scan imports the new ones the same way a FIT upload does. */
export function FolderImport() {
  const [load, retry] = useLoad<FolderImportState>(getFolderImport)
  const [shown, setShown] = useState<FolderImportState | null>(null)
  const [path, setPath] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const running = shown?.running ?? false

  useEffect(() => {
    if (!running) return
    const t = setInterval(() => getFolderImport().then(setShown, () => {}), POLL_MS)
    return () => clearInterval(t)
  }, [running])

  const act = async (fn: () => Promise<FolderImportState>) => {
    setBusy(true)
    setError("")
    try {
      setShown(await fn())
      return true
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      return false
    } finally {
      setBusy(false)
    }
  }

  return (
    <Panel title="Folder import" load={load} retry={retry}>
      {(loaded) => {
        const f = shown ?? loaded
        return (
          <div id="folder-import" className="space-y-3 text-sm">
            <p>
              Rides from a folder of .fit files, without going through intervals.icu. Point it at the folder your bike
              computer or app saves to. Shepherd copies new files in, skips rides it already has, and never changes or
              deletes the files in the folder. Up to {f.max_files} new files per scan; scans also run after each sync.
            </p>
            <p className="text-muted-foreground">
              The path is on the machine Shepherd runs on. If you run Shepherd in Docker, it must be a folder inside a
              mounted volume (for example <code>/data/fit</code>).
            </p>
            {f.folder ? (
              <p>
                Folder: <code className="break-all">{f.folder}</code>
                {f.recursive ? " (and its subfolders)" : ""}
              </p>
            ) : (
              <p className="text-muted-foreground">No folder set.</p>
            )}
            <div className="flex flex-wrap items-end gap-2">
              <Label className="flex-col items-start gap-1">
                Folder with your .fit files
                <Input className="w-80" placeholder="/home/you/FIT" value={path} onChange={(e) => setPath(e.target.value)} />
              </Label>
              <Button size="sm" disabled={busy || !path.trim()} onClick={() => act(() => saveFolderImport({ folder: path.trim() })).then((ok) => ok && setPath(""))}>
                {f.folder ? "Change folder" : "Set folder"}
              </Button>
              {f.folder && (
                <Button size="sm" variant="outline" disabled={busy || running} onClick={() => act(() => saveFolderImport({ folder: "" }))}>
                  Remove folder
                </Button>
              )}
            </div>
            {f.folder && (
              <>
                <Label className="gap-2">
                  <Checkbox checked={f.recursive} disabled={busy || running} onCheckedChange={(v) => act(() => saveFolderImport({ recursive: v === true }))} />
                  Include subfolders (links to other folders are not followed)
                </Label>
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    size="sm"
                    disabled={busy || running}
                    onClick={() =>
                      act(async () => {
                        await startFolderScan()
                        return { ...f, running: true }
                      })
                    }
                  >
                    {running ? "Scanning…" : "Scan now"}
                  </Button>
                  {!running && f.last_scan && (
                    <p role="status">
                      Last scan {f.last_scan.finished_at.replace("T", " ").slice(0, 16)}: {scanSummary(f.last_scan)}
                    </p>
                  )}
                </div>
                {!running && (f.last_scan?.failures?.length ?? 0) > 0 && (
                  <ul className="list-disc pl-5 text-muted-foreground">
                    {f.last_scan!.failures!.map((x) => (
                      <li key={x.file}>
                        <code className="break-all">{x.file}</code>: {x.reason}
                      </li>
                    ))}
                  </ul>
                )}
              </>
            )}
            {error && <p role="alert">{error}</p>}
          </div>
        )
      }}
    </Panel>
  )
}
