import { useCallback, useState } from "react"

import type { PowerCurve, RideSummary, WellnessDay } from "@/api/types"
import { fmtDuration, getFitness, getPowerCurve, getRides, RANGES, type Series } from "@/lib/analysis"
import { fmtMinutes } from "@/lib/home"
import { rideRoute } from "@/lib/rides"
import { LineChart } from "@/screens/Chart"
import { EnergySystems } from "@/screens/EnergySystems"
import { HistoryBackfill } from "@/screens/HistoryBackfill"
import { Panel, useLoad } from "@/screens/panel"
import { PowerModel } from "@/screens/PowerModel"
import { WeightTrend } from "@/screens/WeightTrend"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/native-select"
import { RideTools } from "@/screens/RideTools"
import { BanisterCard, FatigueCard, TauFitsCard } from "@/screens/TrainingModels"

const Range = ({ value, onChange, label }: { value: number; onChange: (n: number) => void; label: string }) => (
  <Label className="flex items-center gap-2 text-sm">
    {label}
    <NativeSelect  value={value} onChange={(e) => onChange(Number(e.target.value))}>
      {RANGES.map(([d, t]) => (
        <option key={d} value={d}>
          {t}
        </option>
      ))}
    </NativeSelect>
  </Label>
)

function Fitness() {
  const [days, setDays] = useState(90)
  const fetcher = useCallback(() => getFitness(days), [days])
  const [load, retry] = useLoad<WellnessDay[]>(fetcher)
  return (
    <Panel title="Fitness and form" load={load} retry={retry}>
      {(rows) => {
        const pts = (key: "ctl" | "atl" | "tsb") =>
          rows.flatMap((r, i) => (r[key] == null ? [] : [{ x: i, y: r[key] as number }]))
        const last = [...rows].reverse().find((r) => r.ctl != null)
        const series: Series[] = [
          { name: "Fitness (CTL)", color: "var(--chart-2)", points: pts("ctl") },
          { name: "Fatigue (ATL)", color: "var(--chart-5)", points: pts("atl") },
          { name: "Form (TSB)", color: "var(--primary)", points: pts("tsb") },
        ]
        return (
          <div className="space-y-3">
            <Range value={days} onChange={setDays} label="Range" />
            {!last ? (
              <p className="text-sm">No fitness data in this range yet.</p>
            ) : (
              <>
                <p className="text-sm">
                  Latest ({last.date}): fitness {Math.round(last.ctl!)} · fatigue {Math.round(last.atl ?? 0)} · form {last.tsb != null ? Math.round(last.tsb) : "—"}
                </p>
                <LineChart
                  series={series}
                  unit="TSS/day"
                  summary={`Fitness, fatigue and form over ${rows.length} days. Latest fitness ${Math.round(last.ctl!)}, fatigue ${Math.round(last.atl ?? 0)}.`}
                />
              </>
            )}
          </div>
        )
      }}
    </Panel>
  )
}

const TICKS = [5, 60, 300, 1200, 3600]

function Power() {
  const [days, setDays] = useState(90)
  const fetcher = useCallback(() => getPowerCurve(days), [days])
  const [load, retry, refresh] = useLoad<PowerCurve>(fetcher)
  return (
    <Panel title="Power curve" load={load} retry={retry}>
      {(c) => {
        const rider = c.rider_curve
        if (!rider.length)
          return (
            <div className="space-y-3">
              <Range value={days} onChange={setDays} label="Range" />
              <p className="text-sm">No power data in this range yet{c.needs_backfill ? ". Your rides have not been read for power yet." : "."}</p>
              {c.needs_backfill && <HistoryBackfill onFinished={refresh} />}
            </div>
          )
        const series: Series[] = [
          { name: "Your best", color: "var(--chart-2)", points: rider.map((p) => ({ x: Math.log(p.duration_s), y: p.watts })) },
          { name: "Reference (current weight)", color: "var(--muted-foreground)", points: c.pg_2011_baseline.map((p) => ({ x: Math.log(p.duration_s), y: p.watts_at_current_weight })) },
        ]
        const at = (s: number) => rider.find((p) => p.duration_s === s)
        return (
          <div className="space-y-3">
            <Range value={days} onChange={setDays} label="Range" />
            <LineChart series={series} unit="W" summary={`Best power for each duration over ${c.n_rides} rides, against a reference curve.`} />
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-3">
              {TICKS.map((s) => (
                <div key={s} className="flex justify-between gap-2">
                  <dt className="text-muted-foreground">{fmtDuration(s)}</dt>
                  <dd>{at(s) ? `${at(s)!.watts} W` : "—"}</dd>
                </div>
              ))}
              {c.cp_w != null && (
                <div className="flex justify-between gap-2">
                  <dt className="text-muted-foreground">Critical power</dt>
                  <dd>{Math.round(c.cp_w)} W</dd>
                </div>
              )}
            </dl>
          </div>
        )
      }}
    </Panel>
  )
}

const day = (iso?: string | null) => (iso ? new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "—")

function Rides() {
  const fetcher = useCallback(() => getRides(20), [])
  const [load, retry, refresh] = useLoad<RideSummary[]>(fetcher)
  return (
    <Panel title="Recent rides" load={load} retry={retry}>
      {(rides) => (
        <div className="space-y-3">
          <RideTools onChanged={refresh} />
          {rides.length === 0 ? (
            <p className="text-sm">No rides yet. Import a FIT file or sync from intervals.icu.</p>
          ) : (
          <ul className="divide-y">
            {rides.map((r) => (
              <li key={r.ride_id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
                <a className="underline-offset-2 hover:underline" href={rideRoute(r.ride_id)}>
                  {day(r.started_at)} · {r.name || "Ride"}
                </a>
                <span className="text-muted-foreground">
                  {r.duration_s ? fmtMinutes(Math.round(r.duration_s / 60)) : "—"}
                  {r.distance_km ? ` · ${Math.round(r.distance_km * 10) / 10} km` : ""}
                  {r.np_w ? ` · ${r.np_w} W NP` : r.avg_power_w ? ` · ${r.avg_power_w} W` : ""}
                  {r.tss != null ? ` · ${Math.round(r.tss)} TSS` : ""}
                </span>
              </li>
            ))}
          </ul>
          )}
        </div>
      )}
    </Panel>
  )
}

export function Analysis() {
  return (
    <div className="grid gap-4 lg:grid-cols-2" aria-label="Analysis">
      <Fitness />
      <Power />
      <EnergySystems />
      <FatigueCard />
      <TauFitsCard />
      <BanisterCard />
      <WeightTrend /><PowerModel />
      <div className="lg:col-span-2">
        <Rides />
      </div>
    </div>
  )
}
