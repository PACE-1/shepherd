import { useCallback, useState } from "react"

import type { RacePrediction, RacePredictor as Data } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { NativeSelect } from "@/components/ui/native-select"
import { getRacePredictor, parseRaceTime, raceTime, type RaceTarget } from "@/lib/predict"
import { formatClock } from "@/lib/sports"
import { Panel, useLoad } from "@/screens/panel"

const RACES = [
  { race: "5k", label: "5K" },
  { race: "10k", label: "10K" },
  { race: "half", label: "Half marathon" },
  { race: "marathon", label: "Marathon" },
]

const STATUS: Record<string, string> = {
  not_enough_long_run: "Not enough long-run history",
  out_of_range: "Outside the model's range",
  not_supported: "Not supported by this model",
}

function Table({ label, rows }: { label: string; rows: RacePrediction[] }) {
  return (
    <table className="w-full" aria-label={label}>
      <tbody>
        {rows.map((p) => (
          <tr key={p.race} className="align-top">
            <td className="pr-2">{p.label}</td>
            <td className="pr-2 whitespace-nowrap">
              {p.status === "ok" && p.time_s != null ? `${raceTime(p.time_s)} (${formatClock(p.pace_s_per_km ?? 0)} /km)` : STATUS[p.status] ?? p.status}
            </td>
            <td className="text-xs text-muted-foreground">{[p.range_text, ...(p.notes ?? [])].filter(Boolean).join(" ")}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function Gap({ target }: { target: NonNullable<Data["target"]> }) {
  const { riegel, critical_speed: cs } = target
  const goal = raceTime(target.target_time_s)
  return (
    <div className="space-y-1" aria-label="Target gap">
      {riegel && (
        <p>
          {riegel.faster_pct > 0
            ? `Riegel: your best recent run would have to be ${riegel.faster_pct}% faster (${raceTime(riegel.current_time_s)} to ${raceTime(riegel.needed_time_s)}) to predict ${goal}.`
            : `Riegel: your best recent run already predicts ${goal} or faster (by ${Math.abs(riegel.faster_pct)}%).`}
        </p>
      )}
      {cs && (
        <p>
          {cs.higher_pct > 0
            ? `Critical speed: it would have to be ${cs.higher_pct}% higher (${formatClock(1000 / cs.current_cs_m_per_s)} to ${formatClock(1000 / cs.needed_cs_m_per_s)} /km), with D′ held fixed.`
            : `Critical speed: yours already covers ${goal} (by ${Math.abs(cs.higher_pct)}%).`}
        </p>
      )}
      {!riegel && !cs && <p>No model can say: it needs a recent run or a saved critical speed (critical speed covers 5K and 10K, 2 to 30 minutes).</p>}
    </div>
  )
}

function TargetForm({ races, onSet }: { races: { race: string; label: string }[]; onSet: (t: RaceTarget | undefined) => void }) {
  const [race, setRace] = useState(races[0]?.race ?? "5k")
  const [text, setText] = useState("")
  const [error, setError] = useState("")
  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!text.trim()) {
      setError("")
      return onSet(undefined)
    }
    const t = parseRaceTime(text)
    if (t == null) return setError("Enter a time like 19:50 or 1:46:39.")
    setError("")
    onSet({ race, time_s: t })
  }
  return (
    <form className="flex flex-wrap items-end gap-2" onSubmit={submit} aria-label="Target time">
      <label className="space-y-1">
        <span className="block text-xs text-muted-foreground">Race</span>
        <NativeSelect size="sm" value={race} onChange={(e) => setRace(e.target.value)} aria-label="Target race">
          {races.map((r) => <option key={r.race} value={r.race}>{r.label}</option>)}
        </NativeSelect>
      </label>
      <label className="space-y-1">
        <span className="block text-xs text-muted-foreground">Target time</span>
        <Input className="h-8 w-28" value={text} onChange={(e) => setText(e.target.value)} placeholder="19:50" aria-label="Target time" />
      </label>
      <Button size="sm" type="submit">Check</Button>
      {error && <span role="alert" className="text-xs text-destructive">{error}</span>}
    </form>
  )
}

function Body({ data, onTarget }: { data: Data; onTarget: (t: RaceTarget | undefined) => void }) {
  const riegel = data.predictions?.filter((p) => p.model === "riegel") ?? []
  const cs = data.predictions?.filter((p) => p.model === "critical_speed") ?? []
  const b = data.best_run
  // The same four races whichever model answered; fall back to the fixed list when there is no input at all.
  const races = RACES
  const weeks = Math.round(data.window_days / 7)
  return (
    <div className="space-y-3 text-sm">
      <div className="space-y-1">
        <h3 className="font-medium">Reach a target time</h3>
        <TargetForm races={races} onSet={onTarget} />
        {data.target && <Gap target={data.target} />}
      </div>
      {b && (
        <div className="space-y-1">
          <h3 className="font-medium">From your best recent run (Riegel)</h3>
          <p className="text-muted-foreground">
            Input: {b.name || "Run"} on {b.date}, {(b.distance_m / 1000).toFixed(1)} km in {raceTime(b.time_s)} ({formatClock(b.pace_s_per_km)} /km).
            {data.longest_run_m != null && ` Longest run in ${weeks} weeks: ${(data.longest_run_m / 1000).toFixed(1)} km.`}
          </p>
          <Table label="Riegel predictions" rows={riegel} />
          <p className="text-xs text-muted-foreground">{data.riegel_method} {data.riegel_confidence} {data.long_run_rule}</p>
        </div>
      )}
      {data.critical_speed && (
        <div className="space-y-1">
          <h3 className="font-medium">From critical speed</h3>
          <p className="text-muted-foreground">
            Input: critical speed {formatClock(1000 / data.critical_speed.cs_m_per_s)} /km, D′ {Math.round(data.critical_speed.d_prime_m)} m
            {data.critical_speed.date ? `, test saved ${data.critical_speed.date}` : ""}.
          </p>
          <Table label="Critical-speed predictions" rows={cs} />
          <p className="text-xs text-muted-foreground">{data.cs_method} {data.cs_confidence}</p>
        </div>
      )}
      {data.missing?.map((m) => <p key={m}>{m}</p>)}
    </div>
  )
}

/** 5K to marathon predictions from the best recent run (Riegel 1981) and the saved critical speed (#121). */
export function RacePredictor({ refreshKey = 0 }: { refreshKey?: number }) {
  const [target, setTarget] = useState<RaceTarget | undefined>()
  // A new fetcher re-reads: after a target is set, and after a critical-speed save (refreshKey changes).
  const fetcher = useCallback(() => {
    void refreshKey
    return getRacePredictor(target)
  }, [target, refreshKey])
  const [load, retry] = useLoad<Data>(fetcher)
  return <Panel title="Race predictor" load={load} retry={retry}>{(d) => <Body data={d} onTarget={setTarget} />}</Panel>
}
