import { useState } from "react"

import type { WorkoutDetail, WorkoutRow } from "@/api/types"
import { buttonVariants } from "@/components/ui/button"
import { downloadUrl, getWorkout, minutes, type Outdoor } from "@/lib/library"
import { fitWorkoutUrl } from "@/lib/plan"

// Builder-made workouts are saved as builder_<slug>.zwo; only those have an editable model.
const isBuilt = (file: string) => /^builder_.+\.zwo$/.test(file)

/** The workout as bars: width is time, height is % of FTP. */
export function PowerProfile({ detail }: { detail: WorkoutDetail }) {
  const total = detail.total_seconds || 1
  const top = Math.max(120, ...detail.segments.map((s) => s.pct ?? 0))
  return (
    <svg role="img" aria-label={`Power profile, ${minutes(total / 60)}, peak ${Math.round(top)}% of FTP`} viewBox="0 0 300 60" className="h-16 w-full">
      {detail.segments.map((s, i) => {
        const h = ((s.pct ?? 0) / top) * 58
        return <rect key={i} x={(s.start / total) * 300} y={60 - h} width={Math.max(0.6, (s.duration / total) * 300)} height={h} className="fill-primary/70" />
      })}
    </svg>
  )
}

/** A library row. Opens to the description and power profile; the .zwo downloads from here. */
export function WorkoutCard({ w, outdoor }: { w: WorkoutRow; outdoor?: Outdoor }) {
  const [open, setOpen] = useState(false)
  const [detail, setDetail] = useState<WorkoutDetail | null>(null)
  const [error, setError] = useState("")

  const toggle = async () => {
    setOpen(!open)
    if (open || detail) return
    setError("")
    try {
      setDetail(await getWorkout(w.Category, w.File))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <li className="space-y-2 py-2 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <button type="button" className="text-left font-medium underline-offset-2 hover:underline" aria-expanded={open} onClick={toggle}>
          {w.display_name || w.Name}
        </button>
        <span className="text-muted-foreground">
          {minutes(w["Duration(min)"])} · {Math.round(w.TSS)} TSS · IF {w.IF.toFixed(2)}
        </span>
      </div>
      {open && (
        <div className="space-y-2">
          {error && <p role="alert">Couldn’t load this workout: {error}</p>}
          {!detail && !error && <p className="text-muted-foreground">Loading…</p>}
          {detail && (
            <>
              <PowerProfile detail={detail} />
              <p className="text-muted-foreground">{detail.description}</p>
            </>
          )}
          <div className="flex flex-wrap gap-2">
            <a href={downloadUrl(w.File, outdoor)} download className={buttonVariants({ size: "sm", variant: "outline" })}>
              Download .zwo
            </a>
            <a href={fitWorkoutUrl(w.File, w.display_name || w.Name, w.content_class || "endurance", w["Duration(min)"])} download className={buttonVariants({ size: "sm", variant: "outline" })}>
              Download .fit
            </a>
            {isBuilt(w.File) && (
              <>
                <a href={`#/builder/${encodeURIComponent(w.File)}`} className={buttonVariants({ size: "sm", variant: "outline" })}>
                  Edit
                </a>
                <a href={`#/builder/copy/${encodeURIComponent(w.File)}`} className={buttonVariants({ size: "sm", variant: "outline" })}>
                  Duplicate
                </a>
              </>
            )}
          </div>
        </div>
      )}
    </li>
  )
}
