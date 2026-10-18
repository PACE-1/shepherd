import { useEffect, useRef, useState } from "react"

import type { BackfillHistoryStatus } from "@/api/types"
import { Button } from "@/components/ui/button"
import { historyStatus, startHistory } from "@/lib/settings"

/** Reads the power data of older rides so the power curve can be drawn. Runs in the background; this shows its progress. */
export function HistoryBackfill({ onFinished, pollMs = 2500 }: { onFinished: () => void; pollMs?: number }) {
  const [task, setTask] = useState<string | null>(null)
  const [status, setStatus] = useState<BackfillHistoryStatus | null>(null)
  const [error, setError] = useState("")
  const finished = useRef(onFinished)
  useEffect(() => {
    finished.current = onFinished
  })

  useEffect(() => {
    if (!task) return
    let live = true
    let timer: ReturnType<typeof setTimeout>
    const poll = async () => {
      try {
        const s = await historyStatus(task)
        if (!live) return
        setStatus(s)
        if (s.state === "done" || s.state === "error") {
          if (s.state === "error") setError("The backfill stopped with an error. Check the log in Settings.")
          setTask(null)
          finished.current()
          return
        }
      } catch (e) {
        if (!live) return
        setError(e instanceof Error ? e.message : String(e))
        setTask(null)
        return
      }
      timer = setTimeout(poll, pollMs)
    }
    poll()
    return () => { live = false; clearTimeout(timer) }
  }, [task, pollMs])

  const start = async () => {
    setError("")
    setStatus(null)
    try {
      const r = await startHistory()
      if (r.task_id) setTask(r.task_id)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }
  const running = task !== null
  return (
    <div className="space-y-2 text-sm">
      <Button size="sm" disabled={running} onClick={start}>
        {running ? "Reading your rides…" : "Build power history"}
      </Button>
      {running && status && (
        <p role="status">
          {status.backfilled} read{status.already_cached ? `, ${status.already_cached} already stored` : ""}{status.failed ? `, ${status.failed} failed` : ""}
          {status.total ? ` of ${status.total}` : ""}.
        </p>
      )}
      {!running && status?.state === "done" && <p role="status">Done: {status.backfilled} rides read{status.failed ? `, ${status.failed} failed` : ""}.</p>}
      {error && <p role="alert">{error}</p>}
    </div>
  )
}
