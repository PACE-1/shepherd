import { useState } from "react"

import type { Balance, BalanceBucket } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/native-select"
import { getBalance, hours, LIMITERS, NAME, parseTargets, saveBalanceTargets, SPORTS, summarise, type Sport } from "@/lib/balance"
import { Panel, useLoad } from "@/screens/panel"

// Four sports, so four colours from the chart tokens; a gap in the card colour separates the segments, and the table and legend carry the names.
const COLOR: Record<Sport, string> = { cycling: "var(--chart-3)", running: "var(--chart-5)", swimming: "var(--chart-1)", other: "var(--muted-foreground)" }

const pct = (v: number | null | undefined) => (v == null ? "–" : `${v}%`)
const gap = (v: number | undefined) => (v === undefined ? "–" : `${v > 0 ? "+" : ""}${v} pp`)

/** Weekly hours stacked by sport. `summary` is the text alternative for the whole chart. */
function StackedWeeks({ weeks, summary }: { weeks: BalanceBucket[]; summary: string }) {
  const W = 300, H = 100, gapX = 2
  const max = Math.max(1, ...weeks.map((w) => w.total_hours))
  const bw = W / weeks.length - gapX
  return (
    <figure className="space-y-1">
      <svg role="img" aria-label={summary} viewBox={`0 0 ${W} ${H}`} className="h-32 w-full">
        {weeks.map((w, i) => {
          let y = H
          return (
            <g key={w.key}>
              <title>{`Week of ${w.start}: ${hours(w.total_hours)}`}</title>
              {SPORTS.filter((s) => w.hours[s] > 0).map((s) => {
                const hgt = (w.hours[s] / max) * H
                y -= hgt
                return <rect key={s} x={i * (bw + gapX)} y={y} width={bw} height={hgt} style={{ fill: COLOR[s], stroke: "var(--card)" }} strokeWidth={1} />
              })}
            </g>
          )
        })}
      </svg>
      <figcaption className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
        <span className="flex flex-wrap gap-3">
          {SPORTS.map((s) => (
            <span key={s} className="flex items-center gap-1">
              <span aria-hidden className="inline-block h-2 w-3 rounded-sm" style={{ background: COLOR[s] }} />
              {NAME[s]}
            </span>
          ))}
        </span>
        <span>0 to {Math.round(max * 10) / 10} h a week</span>
      </figcaption>
    </figure>
  )
}

function Compare({ data }: { data: Balance }) {
  const week = data.weeks[data.weeks.length - 1]
  const month = data.months[data.months.length - 1]
  const rows = SPORTS.filter((s) => data.sports_present.includes(s) || (data.targets?.[s] ?? 0) > 0 || data.limiter === s)
  if (!rows.length) return null
  const cols = data.has_targets
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <caption className="pb-1 text-left text-xs text-muted-foreground">This week so far ({week.start} on) and this month ({month.label}), hours, share of hours and training load</caption>
        <thead>
          <tr className="text-left text-muted-foreground">
            <th className="font-normal">Sport</th>
            <th className="font-normal">This week</th>
            <th className="font-normal">This month</th>
            {cols && <><th className="font-normal">Target</th><th className="font-normal">Week gap</th><th className="font-normal">Month gap</th></>}
          </tr>
        </thead>
        <tbody>
          {rows.map((s) => (
            <tr key={s} className={data.limiter === s ? "font-semibold" : undefined}>
              <td>{NAME[s]}{data.limiter === s && " (limiter)"}</td>
              <td>{hours(week.hours[s])} · {pct(week.hours_share[s])}<span className="block text-xs font-normal text-muted-foreground">load {Math.round(week.load[s])}</span></td>
              <td>{hours(month.hours[s])} · {pct(month.hours_share[s])}<span className="block text-xs font-normal text-muted-foreground">load {Math.round(month.load[s])}</span></td>
              {cols && <><td>{pct(data.targets?.[s])}</td><td>{gap(week.gap_pp?.[s])}</td><td>{gap(month.gap_pp?.[s])}</td></>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Targets({ data, onSaved }: { data: Balance; onSaved: () => void }) {
  const [text, setText] = useState<Record<string, string>>(() => Object.fromEntries(SPORTS.map((s) => [s, data.targets ? String(data.targets[s]) : ""])))
  const [limiter, setLimiter] = useState(data.limiter ?? "")
  const [error, setError] = useState("")
  const [msg, setMsg] = useState("")
  const sum = SPORTS.reduce((a, s) => a + (Number(text[s]) || 0), 0)
  const save = async () => {
    setError("")
    setMsg("")
    const p = parseTargets(text)
    if (p.error) return setError(p.error)
    try {
      await saveBalanceTargets(p.targets, limiter || null)
      setMsg(p.targets ? "Saved." : "Saved. No target split is set.")
      onSaved()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }
  return (
    <div className="space-y-2 text-sm">
      <h3 className="font-medium">Your target split</h3>
      <p className="text-muted-foreground">Percent of your weekly hours for each sport, adding up to 100. Leave every box empty for no target.</p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {SPORTS.map((s) => (
          <div key={s} className="space-y-1">
            <Label htmlFor={`bal-${s}`}>{NAME[s]} target (%)</Label>
            <Input id={`bal-${s}`} inputMode="decimal" value={text[s] ?? ""} onChange={(e) => setText({ ...text, [s]: e.target.value })} />
          </div>
        ))}
      </div>
      <p className="text-xs text-muted-foreground">Adds up to {Math.round(sum * 10) / 10}.</p>
      <div className="space-y-1">
        <Label htmlFor="bal-limiter">Your limiter (optional)</Label>
        <NativeSelect id="bal-limiter" value={limiter} onChange={(e) => setLimiter(e.target.value)}>
          <option value="">None</option>
          {LIMITERS.map((s) => <option key={s} value={s}>{NAME[s]}</option>)}
        </NativeSelect>
        <p className="text-xs text-muted-foreground">{data.limiter_note}</p>
      </div>
      <Button size="sm" onClick={save}>Save targets</Button>
      {error && <p role="alert">{error}</p>}
      {msg && <p role="status">{msg}</p>}
    </div>
  )
}

function Body({ data, onSaved }: { data: Balance; onSaved: () => void }) {
  const week = data.weeks[data.weeks.length - 1]
  const month = data.months[data.months.length - 1]
  const summary = summarise(data.weeks)
  return (
    <div className="space-y-3 text-sm">
      {!data.has_history && <p className="text-muted-foreground">No activities in the last {data.weeks.length} weeks yet. The chart fills in once rides, runs or swims sync.</p>}
      {data.single_sport && (
        <p>All {NAME[data.single_sport as Sport].toLowerCase()}: {hours(week.total_hours)} this week so far, {hours(month.total_hours)} this month.</p>
      )}
      {data.has_history && (
        <>
          <StackedWeeks weeks={data.weeks} summary={summary} />
          <p className="text-muted-foreground">{summary}</p>
        </>
      )}
      <Compare data={data} />
      {!data.has_targets && data.has_history && !data.single_sport && <p className="text-muted-foreground">Set a target split below to see the gap for each sport.</p>}
      <Targets data={data} onSaved={onSaved} />
      <p className="text-xs text-muted-foreground">{data.method}</p>
    </div>
  )
}

/** Hours and load by sport for the last 12 weeks, this week and month against the rider's own target split. */
export function SportBalance() {
  const [load, retry, refresh] = useLoad<Balance>(getBalance)
  return <Panel title="Sport balance" load={load} retry={retry}>{(d) => <Body data={d} onSaved={refresh} />}</Panel>
}
