import { useState } from "react"

import type { PlanCompanion } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { fmtClock, parseClock, saveBrickNote, saveTransition } from "@/lib/companions"
import { isoDay } from "@/lib/home"

/** A brick run's extras: it follows the ride, the rider's transition-time target, and (once its day has
 * come) the rider's note on how the run felt off the bike. */
export function BrickDetails({ c, target, onSaved }: { c: PlanCompanion; target: number | null; onSaved: () => void }) {
  const [t, setT] = useState(target != null ? fmtClock(target) : "")
  const [note, setNote] = useState(c.brick_note ?? "")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const parsed = parseClock(t)
  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    setError("")
    try {
      await fn()
      onSaved()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <span className="mt-1 block space-y-2 text-xs">
      <span className="block text-muted-foreground">
        Run straight after the ride.{" "}
        {target != null ? `Your transition target: ${fmtClock(target)}.` : "No transition target set."}
      </span>
      <span className="flex flex-wrap items-end gap-2">
        <Label className="flex-col items-start gap-1">
          Transition target (m:ss)
          <Input className="h-8 max-w-24" value={t} placeholder="m:ss" onChange={(e) => setT(e.target.value)} />
        </Label>
        <Button size="sm" variant="outline" disabled={busy || parsed === undefined} onClick={() => run(() => saveTransition(parsed ?? null))}>
          Save target
        </Button>
        {parsed === undefined && <span className="text-muted-foreground">Type m:ss, from 0:01 to 60:00.</span>}
      </span>
      {c.day <= isoDay() && (
        <span className="flex flex-wrap items-end gap-2">
          <Label className="w-full flex-col items-start gap-1">
            How did the run feel off the bike?
            <textarea
              value={note}
              maxLength={500}
              rows={2}
              onChange={(e) => setNote(e.target.value)}
              className="w-full rounded-lg border border-input bg-background px-3 py-1 text-sm dark:bg-input/30"
            />
          </Label>
          <Button size="sm" variant="outline" disabled={busy || note.trim() === (c.brick_note ?? "")} onClick={() => run(() => saveBrickNote(c.id, note))}>
            Save note
          </Button>
        </span>
      )}
      {error && <span role="alert" className="block">Couldn’t save: {error}</span>}
    </span>
  )
}
