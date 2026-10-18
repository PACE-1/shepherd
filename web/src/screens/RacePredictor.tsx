import type { RacePrediction, RacePredictor as Data } from "@/api/types"
import { getRacePredictor, raceTime } from "@/lib/predict"
import { formatClock } from "@/lib/sports"
import { Panel, useLoad } from "@/screens/panel"

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

function Body({ data }: { data: Data }) {
  const riegel = data.predictions?.filter((p) => p.model === "riegel") ?? []
  const cs = data.predictions?.filter((p) => p.model === "critical_speed") ?? []
  const b = data.best_run
  const weeks = Math.round(data.window_days / 7)
  return (
    <div className="space-y-3 text-sm">
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
export function RacePredictor() {
  const [load, retry] = useLoad<Data>(getRacePredictor)
  return <Panel title="Race predictor" load={load} retry={retry}>{(d) => <Body data={d} />}</Panel>
}
