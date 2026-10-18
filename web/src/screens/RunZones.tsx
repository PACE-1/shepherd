import { useState } from "react"

import type { CriticalSpeed, RunActivities, RunGap, RunZones as Zones } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { bpmRange, criticalSpeed, getRunActivities, getRunZones, gradeAdjusted, paceRange, type Trial } from "@/lib/run"
import { formatClock, parseClock } from "@/lib/sports"
import { Panel, useLoad } from "@/screens/panel"

const errText = (e: unknown) => (e instanceof Error ? e.message : String(e))

function ZoneTables({ data }: { data: Zones }) {
  return (
    <div className="space-y-3 text-sm">
      {data.pace_zones?.length ? (
        <table className="w-full" aria-label="Pace zones">
          <caption className="text-left text-muted-foreground">Pace, from threshold {formatClock(data.threshold_pace_s_per_km ?? 0)} /km</caption>
          <tbody>
            {data.pace_zones.map((z) => (
              <tr key={z.zone}><td>Z{z.zone}</td><td>{z.name}</td><td>{paceRange(z.slow_s_per_km, z.fast_s_per_km)}</td></tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p>Set a run threshold pace, or save a critical speed below, to see pace zones.</p>
      )}
      {data.hr_zones?.length ? (
        <table className="w-full" aria-label="Heart-rate zones">
          <caption className="text-left text-muted-foreground">Heart rate, from threshold {Math.round(data.threshold_hr ?? 0)} bpm</caption>
          <tbody>
            {data.hr_zones.map((z) => (
              <tr key={z.zone}><td>Z{z.zone}</td><td>{z.name}</td><td>{bpmRange(z.low_bpm, z.high_bpm)}</td></tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p>Set a run threshold heart rate to see heart-rate zones.</p>
      )}
      <p className="text-xs text-muted-foreground">{data.method} {data.confidence}</p>
    </div>
  )
}

function CriticalSpeedTest({ onSaved }: { onSaved: () => void }) {
  const [rows, setRows] = useState([{ d: "", t: "" }, { d: "", t: "" }, { d: "", t: "" }])
  const [result, setResult] = useState<CriticalSpeed | null>(null)
  const [error, setError] = useState("")
  const [msg, setMsg] = useState("")
  const trials = (): Trial[] | null => {
    const filled = rows.filter((r) => r.d.trim() || r.t.trim())
    const out = filled.map((r) => ({ distance_m: /^\d+(\.\d+)?$/.test(r.d.trim()) ? Number(r.d) : NaN, time_s: parseClock(r.t) ?? NaN }))
    return out.length >= 2 && out.every((x) => x.distance_m > 0 && x.time_s > 0) ? out : null
  }
  const run = async (save: boolean) => {
    setError("")
    setMsg("")
    const t = trials()
    if (!t) return setError("Enter two or three trials: distance in metres and time as minutes:seconds.")
    try {
      const r = await criticalSpeed(t, save)
      setResult(r)
      if (r.saved) {
        setMsg(`Saved ${formatClock(r.cs_pace_s_per_km)} /km as your run threshold pace.`)
        onSaved()
      }
    } catch (e) {
      setResult(null)
      setError(errText(e))
    }
  }
  const set = (i: number, k: "d" | "t", v: string) => setRows(rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)))
  return (
    <div className="space-y-3 text-sm">
      <p className="text-muted-foreground">Run two or three all-out efforts of about 2 to 15 minutes on separate days, for example 1200 m and 3600 m. The third is optional.</p>
      {rows.map((r, i) => (
        <div key={i} className="flex flex-wrap items-end gap-2">
          <div className="space-y-1">
            <Label htmlFor={`cs-d${i}`}>Trial {i + 1} distance (m)</Label>
            <Input id={`cs-d${i}`} value={r.d} onChange={(e) => set(i, "d", e.target.value)} className="max-w-28" inputMode="numeric" />
          </div>
          <div className="space-y-1">
            <Label htmlFor={`cs-t${i}`}>Trial {i + 1} time (m:ss)</Label>
            <Input id={`cs-t${i}`} value={r.t} onChange={(e) => set(i, "t", e.target.value)} className="max-w-28" />
          </div>
        </div>
      ))}
      <div className="flex gap-2">
        <Button size="sm" onClick={() => run(false)}>Calculate</Button>
        {result && !result.saved && <Button size="sm" variant="outline" onClick={() => run(true)}>Use as threshold pace</Button>}
      </div>
      {result && (
        <div className="space-y-1" aria-label="Critical speed result">
          <p>Critical speed {formatClock(result.cs_pace_s_per_km)} /km ({result.cs_m_per_s} m/s), D′ {Math.round(result.d_prime_m)} m{result.r2 != null ? `, R² ${result.r2}` : ""}</p>
          {result.warnings?.map((w) => <p key={w}>{w}</p>)}
          <p className="text-xs text-muted-foreground">{result.method} {result.confidence}</p>
        </div>
      )}
      {error && <p role="alert">{error}</p>}
      {msg && <p role="status">{msg}</p>}
    </div>
  )
}

function GradeAdjusted() {
  const [pace, setPace] = useState("")
  const [grade, setGrade] = useState("")
  const [out, setOut] = useState<RunGap | null>(null)
  const [error, setError] = useState("")
  const go = async () => {
    setError("")
    const p = parseClock(pace)
    const g = /^\s*-?\d+(\.\d+)?\s*$/.test(grade) ? Number(grade) : null
    if (p === null || g === null) return setError("Enter a pace as minutes:seconds and a gradient in percent, like 5 or -8.")
    try {
      setOut(await gradeAdjusted(p, g))
    } catch (e) {
      setOut(null)
      setError(errText(e))
    }
  }
  return (
    <div className="space-y-3 text-sm">
      <div className="flex flex-wrap items-end gap-2">
        <div className="space-y-1">
          <Label htmlFor="gap-pace">Pace on the slope (m:ss /km)</Label>
          <Input id="gap-pace" value={pace} onChange={(e) => setPace(e.target.value)} className="max-w-28" />
        </div>
        <div className="space-y-1">
          <Label htmlFor="gap-grade">Gradient (%)</Label>
          <Input id="gap-grade" value={grade} onChange={(e) => setGrade(e.target.value)} className="max-w-28" />
        </div>
        <Button size="sm" onClick={go}>Convert</Button>
      </div>
      {out && (
        <div className="space-y-1">
          <p>Equal effort on the flat: {formatClock(out.gap_s_per_km)} /km</p>
          <p className="text-xs text-muted-foreground">{out.method} {out.confidence}</p>
        </div>
      )}
      {error && <p role="alert">{error}</p>}
    </div>
  )
}

const num = (v: number | null | undefined, digits = 0) => (v == null ? "–" : v.toFixed(digits))

function Runs({ data }: { data: RunActivities }) {
  return (
    <div className="space-y-2 text-sm">
      {data.runs?.length ? (
        <div className="overflow-x-auto">
          <table className="w-full" aria-label="Recent runs">
            <thead>
              <tr className="text-left text-muted-foreground">
                <th className="font-normal">Date</th><th className="font-normal">Run</th><th className="font-normal">km</th><th className="font-normal">Pace</th>
                <th className="font-normal">rTSS</th><th className="font-normal">hrTSS</th><th className="font-normal">intervals.icu</th>
                <th className="font-normal">Cadence</th><th className="font-normal">Stride (m)</th>
              </tr>
            </thead>
            <tbody>
              {data.runs.map((r) => (
                <tr key={r.id}>
                  <td>{r.date}</td><td>{r.name}</td><td>{num(r.distance_km, 1)}</td>
                  <td>{r.pace_s_per_km ? formatClock(r.pace_s_per_km) : "–"}</td>
                  <td>{num(r.rtss)}</td><td>{num(r.hrtss)}</td><td>{num(r.icu_load)}</td>
                  <td>{r.cadence_spm ? `${Math.round(r.cadence_spm)} spm${r.cadence_doubled ? "*" : ""}` : "–"}</td>
                  <td>{num(r.stride_length_m, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p>No runs in the last 90 days.</p>
      )}
      {data.runs?.some((r) => r.cadence_doubled) && <p className="text-xs text-muted-foreground">* recorded per foot, shown as steps per minute.</p>}
      {data.missing?.map((m) => <p key={m}>{m}</p>)}
      <p className="text-xs text-muted-foreground">{data.method} {data.confidence}</p>
    </div>
  )
}

/** Run zones from the current thresholds, a critical-speed test, grade-adjusted pace and per-run load (#118, #119). */
export function RunZones() {
  const [zones, retryZones, refreshZones] = useLoad<Zones>(getRunZones)
  const [runs, retryRuns, refreshRuns] = useLoad<RunActivities>(getRunActivities)
  const saved = () => {
    refreshZones()
    refreshRuns()
  }
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Panel title="Run zones" load={zones} retry={retryZones}>{(d) => <ZoneTables data={d} />}</Panel>
      <Card>
        <CardContent className="space-y-2 p-4">
          <h2 className="text-sm font-semibold">Critical speed test</h2>
          <CriticalSpeedTest onSaved={saved} />
        </CardContent>
      </Card>
      <Card>
        <CardContent className="space-y-2 p-4">
          <h2 className="text-sm font-semibold">Grade-adjusted pace</h2>
          <GradeAdjusted />
        </CardContent>
      </Card>
      <Panel title="Run load and stride" load={runs} retry={retryRuns}>{(d) => <Runs data={d} />}</Panel>
    </div>
  )
}
