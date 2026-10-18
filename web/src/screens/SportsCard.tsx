import { useState } from "react"

import type { SportThresholds, SportsLoad } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { formatClock, getSportThresholds, getSportsLoad, parseClock, setSportThreshold } from "@/lib/sports"
import { Panel, useLoad } from "@/screens/panel"

const NAME: Record<string, string> = { cycling: "Cycling", running: "Running", swimming: "Swimming", other: "Other" }

const KINDS = [
  { kind: "run_threshold_pace", label: "Run threshold pace (min:sec per km)", clock: true },
  { kind: "run_threshold_hr", label: "Run threshold heart rate (bpm)", clock: false },
  { kind: "swim_css", label: "Swim critical speed (min:sec per 100 m)", clock: true },
] as const

const show = (kind: (typeof KINDS)[number], v: number | null | undefined) =>
  v == null ? "not set" : kind.clock ? `${formatClock(v)} ${kind.kind === "swim_css" ? "/100 m" : "/km"}` : `${Math.round(v)} bpm`

function Load({ data }: { data: SportsLoad }) {
  const rows = [...Object.entries(data.sports).map(([k, v]) => [NAME[k] ?? k, v] as const), ["All sports", data.combined] as const]
  return (
    <div className="space-y-2 text-sm">
      <table className="w-full">
        <thead>
          <tr className="text-left text-muted-foreground">
            <th className="font-normal">Sport</th><th className="font-normal">Fitness</th><th className="font-normal">Fatigue</th><th className="font-normal">Form</th><th className="font-normal">7 days</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([name, l]) => (
            <tr key={name}><td>{name}</td><td>{l.ctl}</td><td>{l.atl}</td><td>{l.tsb}</td><td>{l.week_load}</td></tr>
          ))}
        </tbody>
      </table>
      {!data.settled && <p className="text-muted-foreground">Only {data.days_of_history} days of history, so these numbers are still settling.</p>}
      <p className="text-xs text-muted-foreground">{data.confidence}</p>
    </div>
  )
}

function Thresholds({ data, onSaved }: { data: SportThresholds; onSaved: () => void }) {
  const [text, setText] = useState<Record<string, string>>({})
  const [error, setError] = useState("")
  const [msg, setMsg] = useState("")
  const save = async (k: (typeof KINDS)[number]) => {
    setError("")
    setMsg("")
    const raw = text[k.kind] ?? ""
    const value = k.clock ? parseClock(raw) : /^\d+$/.test(raw.trim()) ? Number(raw) : null
    if (value === null) return setError(k.clock ? "Enter minutes and seconds, like 4:30." : "Enter a whole number.")
    try {
      await setSportThreshold(k.kind, value)
      setText({ ...text, [k.kind]: "" })
      setMsg("Saved.")
      onSaved()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }
  return (
    <div className="space-y-3 text-sm">
      <p className="text-muted-foreground">Cycling FTP is under FTP history.</p>
      {KINDS.map((k) => (
        <div key={k.kind} className="space-y-1">
          <Label htmlFor={k.kind}>{k.label}</Label>
          <p>Now {show(k, data.thresholds[k.kind]?.current)}</p>
          <div className="flex gap-2">
            <Input id={k.kind} value={text[k.kind] ?? ""} onChange={(e) => setText({ ...text, [k.kind]: e.target.value })} className="max-w-32" />
            <Button size="sm" onClick={() => save(k)}>Set</Button>
          </div>
        </div>
      ))}
      {error && <p role="alert">{error}</p>}
      {msg && <p role="status">{msg}</p>}
    </div>
  )
}

/** Training load for each sport and all together, plus the run and swim thresholds. */
export function SportsCard() {
  const [load, retryLoad] = useLoad<SportsLoad>(getSportsLoad)
  const [thr, retryThr, refreshThr] = useLoad<SportThresholds>(getSportThresholds)
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Panel title="Training load by sport" load={load} retry={retryLoad}>{(d) => <Load data={d} />}</Panel>
      <Panel title="Run and swim thresholds" load={thr} retry={retryThr}>{(d) => <Thresholds data={d} onSaved={refreshThr} />}</Panel>
    </div>
  )
}
