import { useCallback, useState } from "react"

import type { RunSession } from "@/api/types"
import { Button, buttonVariants } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/native-select"
import { EMPTY_QUERY, getRunSession, listRunSessions, RUN_TYPES, runDownloadUrl, stepLines, type RunQuery, type RunStep } from "@/lib/runSessions"
import { LineChart } from "@/screens/Chart"
import { useLoad } from "@/screens/panel"

const NOTE = "Design templates after Daniels; not validated against recorded runs."
const num = (v: string) => (v === "" ? null : Number(v))
const errText = (e: unknown) => (e instanceof Error ? e.message : String(e))

/** The chosen session at a chosen length: intensity chart, steps and downloads. */
function Detail({ row }: { row: RunSession }) {
  const [minutes, setMinutes] = useState(row.minutes)
  const [shown, setShown] = useState<RunSession>(row)
  const [error, setError] = useState("")
  const change = (m: number) => {
    setMinutes(m)
    setError("")
    if (m < row.min_minutes || m > row.max_minutes) return setError(`Choose ${row.min_minutes} to ${row.max_minutes} minutes.`)
    getRunSession(row.id, m).then(setShown, (e: unknown) => setError(errText(e)))
  }
  const steps = (shown.workout as { steps: RunStep[] }).steps
  const ok = !error && shown.minutes === minutes
  return (
    <div className="space-y-2 pt-2">
      <Label className="flex-col items-start gap-1 text-sm">
        Length (min)
        <Input type="number" className="w-24" min={row.min_minutes} max={row.max_minutes} step={5} value={minutes} onChange={(e) => change(Number(e.target.value))} />
      </Label>
      {error && <p role="alert" className="text-sm">{error}</p>}
      <LineChart
        series={[{ name: "Intensity (% threshold speed)", color: "var(--primary)", points: shown.profile }]}
        summary={`Intensity profile, ${shown.minutes} minutes`}
        unit="% threshold speed"
      />
      <ol className="list-decimal space-y-0.5 pl-5 text-sm">
        {stepLines(steps).map((l, i) => <li key={i}>{l}</li>)}
      </ol>
      <p className="text-xs text-muted-foreground">Estimated load: about {Math.round(shown.rtss_estimate)} rTSS if run at the intended zones (an estimate).</p>
      {ok && (
        <div className="flex flex-wrap gap-2">
          <a href={runDownloadUrl(row.id, minutes, "fit")} download className={buttonVariants({ size: "sm", variant: "outline" })}>Download .fit</a>
          <a href={runDownloadUrl(row.id, minutes, "txt")} download className={buttonVariants({ size: "sm", variant: "outline" })}>Download text</a>
        </div>
      )}
    </div>
  )
}

function Browser() {
  const [q, setQ] = useState<RunQuery>(EMPTY_QUERY)
  const [open, setOpen] = useState<string | null>(null)
  const fetcher = useCallback(() => listRunSessions(q), [q])
  const [load, retry] = useLoad(fetcher)
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">{NOTE}</p>
      <div className="flex flex-wrap items-end gap-2 text-sm">
        <Label className="flex-col items-start gap-1">
          Stimulus
          <NativeSelect value={q.type} onChange={(e) => setQ({ ...q, type: e.target.value })}>
            <option value="">All types</option>
            {RUN_TYPES.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
          </NativeSelect>
        </Label>
        <Label className="flex-col items-start gap-1">
          From (min)
          <Input type="number" min={0} className="w-24" value={q.minMinutes ?? ""} onChange={(e) => setQ({ ...q, minMinutes: num(e.target.value) })} />
        </Label>
        <Label className="flex-col items-start gap-1">
          To (min)
          <Input type="number" min={0} className="w-24" value={q.maxMinutes ?? ""} onChange={(e) => setQ({ ...q, maxMinutes: num(e.target.value) })} />
        </Label>
        <Label className="flex-col items-start gap-1">
          Up to (rTSS)
          <Input type="number" min={0} className="w-24" value={q.maxRtss ?? ""} onChange={(e) => setQ({ ...q, maxRtss: num(e.target.value) })} />
        </Label>
      </div>
      {load.state === "loading" && <p className="text-sm text-muted-foreground">Loading…</p>}
      {load.state === "error" && (
        <div role="alert" className="text-sm">
          <p>Couldn’t load the run workouts: {load.message}</p>
          <Button className="mt-2" size="sm" variant="outline" onClick={retry}>Retry</Button>
        </div>
      )}
      {load.state === "ok" && (
        <>
          {load.data.targets === "effort" && (
            <p className="text-sm">No run threshold pace is saved, so targets are effort cues. Set one under Settings, Sports, to get paces.</p>
          )}
          {load.data.sessions.length === 0 ? (
            <p className="text-sm">No run workouts match.</p>
          ) : (
            <ul className="divide-y" aria-label="Run workouts">
              {load.data.sessions.map((s) => (
                <li key={s.id} className="py-2">
                  <button type="button" className="w-full text-left" aria-expanded={open === s.id} onClick={() => setOpen(open === s.id ? null : s.id)}>
                    <span className="text-sm font-medium">{s.name}</span>
                    <span className="block text-xs text-muted-foreground">
                      Daniels {s.daniels} · {s.stimulus} · {s.hard ? "hard" : "easy"} · {s.min_minutes} to {s.max_minutes} min · about {Math.round(s.rtss_estimate)} rTSS at {s.minutes} min
                    </span>
                    <span className="block text-sm">{s.intent}</span>
                  </button>
                  {open === s.id && <Detail key={`${s.id}-${s.minutes}`} row={s} />}
                </li>
              ))}
            </ul>
          )}
          <p className="text-xs text-muted-foreground">{load.data.method}</p>
        </>
      )}
    </div>
  )
}

/** Run workouts in the Library: closed until asked for, so the cycling Library loads as before. */
export function RunWorkouts() {
  const [shown, setShown] = useState(false)
  return (
    <Card>
      <CardContent className="space-y-2 p-4">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold">Run workouts</h2>
          <Button size="sm" variant="outline" aria-expanded={shown} onClick={() => setShown(!shown)}>
            {shown ? "Hide" : "Show run workouts"}
          </Button>
        </div>
        {shown && <Browser />}
      </CardContent>
    </Card>
  )
}
