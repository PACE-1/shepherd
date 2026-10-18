import { useCallback, useState } from "react"

import { Button } from "@/components/ui/button"
import { companionStatus, dismissCompanion, getCompanions, NOT_VALIDATED, sportLabel, weekCompanions } from "@/lib/companions"
import { fmtMinutes } from "@/lib/home"
import { useLoad } from "@/screens/panel"

const dayLabel = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })

/** The plan week's runs, swims and strength sessions, under its rides. Renders nothing when there are none. */
export function WeekCompanions({ start }: { start: string }) {
  const fetcher = useCallback(() => getCompanions(start), [start])
  const [load, , refresh] = useLoad(fetcher)
  const [busy, setBusy] = useState("")
  const [error, setError] = useState("")
  if (load.state !== "ok") return null
  const list = weekCompanions(load.data, start)
  if (!list.length) return null

  const dismiss = async (id: string) => {
    setBusy(id)
    setError("")
    try {
      await dismissCompanion(id)
      refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy("")
    }
  }

  return (
    <section aria-label="Other sports this week" className="space-y-1 border-t pt-3">
      <h3 className="text-sm font-semibold">Other sports</h3>
      <p className="text-xs text-muted-foreground">{load.data.note || NOT_VALIDATED}</p>
      <ul className="divide-y">
        {list.map((c) => {
          const status = companionStatus(c)
          return (
            <li key={c.id} className={`flex flex-wrap items-center gap-2 py-2 text-sm ${c.status === "dismissed" ? "opacity-60" : ""}`}>
              <span className="min-w-56 flex-1">
                {dayLabel(c.day)} · <span className="font-medium">{sportLabel(c.sport)}</span>
                <span className="block text-xs text-muted-foreground">{c.description}</span>
              </span>
              <span className="text-muted-foreground">
                {fmtMinutes(c.duration_min ?? 0)}
                {c.hard ? " · hard" : ""}
                {status ? ` · ${status}` : ""}
              </span>
              {c.status === "pending" && (
                <Button size="sm" variant="ghost" disabled={busy === c.id} aria-label={`Dismiss ${sportLabel(c.sport)} ${dayLabel(c.day)}`} onClick={() => dismiss(c.id)}>
                  Dismiss
                </Button>
              )}
            </li>
          )
        })}
      </ul>
      {error && <p role="alert" className="text-sm">Couldn’t dismiss that session: {error}</p>}
    </section>
  )
}
