import { useState } from "react"

import type { SwimActivities, SwimCss, SwimCssTest } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import type { Trial } from "@/lib/run"
import { parseClock } from "@/lib/sports"
import { cssTest, getSwimActivities, getSwimCss, per100, waterLabel } from "@/lib/swim"
import { OpenWaterNotes } from "@/screens/OpenWaterNotes"
import { Panel, useLoad } from "@/screens/panel"

const errText = (e: unknown) => (e instanceof Error ? e.message : String(e))

function Css({ data }: { data: SwimCss }) {
  return (
    <div className="space-y-2 text-sm">
      {data.css_s_per_100m ? <p>CSS {per100(data.css_s_per_100m)}</p> : <p>No swim CSS yet. Save a CSS test, or set it under Training load by sport.</p>}
      {data.history?.length ? (
        <table className="w-full" aria-label="CSS history">
          <tbody>
            {[...data.history].reverse().map((h) => (
              <tr key={h.date}><td>{h.date}</td><td>{per100(h.value)}</td><td className="text-muted-foreground">{h.source === "css_test" ? "CSS test" : h.source}</td></tr>
            ))}
          </tbody>
        </table>
      ) : null}
      <p>{data.zones_note}</p>
      <p className="text-xs text-muted-foreground">{data.method} {data.confidence}</p>
    </div>
  )
}

function CssTest({ onSaved }: { onSaved: () => void }) {
  const [rows, setRows] = useState([{ d: "400", t: "" }, { d: "200", t: "" }])
  const [result, setResult] = useState<SwimCssTest | null>(null)
  const [error, setError] = useState("")
  const [msg, setMsg] = useState("")
  const trials = (): Trial[] | null => {
    const out = rows.map((r) => ({ distance_m: /^\d+(\.\d+)?$/.test(r.d.trim()) ? Number(r.d) : NaN, time_s: parseClock(r.t) ?? NaN }))
    return out.every((x) => x.distance_m > 0 && x.time_s > 0) ? out : null
  }
  const run = async (save: boolean) => {
    setError("")
    setMsg("")
    const t = trials()
    if (!t) return setError("Enter both swims: distance in metres and time as minutes:seconds.")
    try {
      const r = await cssTest(t, save)
      setResult(r)
      if (r.saved) {
        setMsg(`Saved ${per100(r.css_s_per_100m)} as your swim CSS.`)
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
      <p className="text-muted-foreground">Swim 400 m and 200 m all-out and enter both times.</p>
      {rows.map((r, i) => (
        <div key={i} className="flex flex-wrap items-end gap-2">
          <div className="space-y-1">
            <Label htmlFor={`css-d${i}`}>Swim {i + 1} distance (m)</Label>
            <Input id={`css-d${i}`} value={r.d} onChange={(e) => set(i, "d", e.target.value)} className="max-w-28" inputMode="numeric" />
          </div>
          <div className="space-y-1">
            <Label htmlFor={`css-t${i}`}>Swim {i + 1} time (m:ss)</Label>
            <Input id={`css-t${i}`} value={r.t} onChange={(e) => set(i, "t", e.target.value)} className="max-w-28" />
          </div>
        </div>
      ))}
      <div className="flex gap-2">
        <Button size="sm" onClick={() => run(false)}>Work out CSS</Button>
        {result && !result.saved && <Button size="sm" variant="outline" onClick={() => run(true)}>Use as swim CSS</Button>}
      </div>
      {result && (
        <div className="space-y-1" aria-label="CSS result">
          <p>CSS {per100(result.css_s_per_100m)} ({result.css_m_per_s} m/s){result.r2 != null ? `, R² ${result.r2}` : ""}</p>
          <p className="text-xs text-muted-foreground">{result.method} {result.confidence}</p>
        </div>
      )}
      {error && <p role="alert">{error}</p>}
      {msg && <p role="status">{msg}</p>}
    </div>
  )
}

const num = (v: number | null | undefined, digits = 0) => (v == null ? "–" : v.toFixed(digits))

function Swims({ data }: { data: SwimActivities }) {
  return (
    <div className="space-y-2 text-sm">
      {data.swims?.length ? (
        <div className="overflow-x-auto">
          <table className="w-full" aria-label="Recent swims">
            <thead>
              <tr className="text-left text-muted-foreground">
                <th className="font-normal">Date</th><th className="font-normal">Swim</th><th className="font-normal">Where</th><th className="font-normal">m</th>
                <th className="font-normal">Pace</th><th className="font-normal">sTSS</th><th className="font-normal">intervals.icu</th>
                <th className="font-normal">Lengths</th><th className="font-normal">Stroke rate</th>
              </tr>
            </thead>
            <tbody>
              {data.swims.map((s) => (
                <tr key={s.id}>
                  <td>{s.date}</td><td>{s.name}</td><td>{waterLabel(s.water, s.pool_length_m)}</td><td>{num(s.distance_m)}</td>
                  <td>{s.pace_s_per_100m ? per100(s.pace_s_per_100m) : "–"}</td>
                  <td>{num(s.stss)}</td><td>{num(s.icu_load)}</td><td>{num(s.lengths)}</td>
                  <td>{s.stroke_rate ? `${Math.round(s.stroke_rate)} /min` : "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p>No swims in the last 90 days.</p>
      )}
      {data.missing?.map((m) => <p key={m}>{m}</p>)}
      <p className="text-xs text-muted-foreground">{data.method} {data.confidence} {data.stroke_note}</p>
    </div>
  )
}

/** Swim CSS and its test, per-swim sTSS and stroke data (#122), and open-water notes (#126). */
export function SwimZones() {
  const [css, retryCss, refreshCss] = useLoad<SwimCss>(getSwimCss)
  const [swims, retrySwims, refreshSwims] = useLoad<SwimActivities>(getSwimActivities)
  const saved = () => {
    refreshCss()
    refreshSwims()
  }
  const choices = swims.state === "ok" ? (swims.data.swims ?? []).map((s) => ({ id: s.id, date: s.date, name: s.name })) : []
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Panel title="Swim CSS" load={css} retry={retryCss}>{(d) => <Css data={d} />}</Panel>
      <Card>
        <CardContent className="space-y-2 p-4">
          <h2 className="text-sm font-semibold">CSS test</h2>
          <CssTest onSaved={saved} />
        </CardContent>
      </Card>
      <Panel title="Swim load and strokes" load={swims} retry={retrySwims}>{(d) => <Swims data={d} />}</Panel>
      <OpenWaterNotes swims={choices} />
    </div>
  )
}
