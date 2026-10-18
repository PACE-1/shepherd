import { useCallback, useState } from "react"

import type { PowerModel as Model } from "@/api/types"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/native-select"
import { fmtDuration } from "@/lib/analysis"
import { getPowerModel } from "@/lib/analytics"
import { LineChart } from "@/screens/Chart"
import { Panel, Row, useLoad } from "@/screens/panel"

const WINDOWS = [
  [42, "6 weeks"],
  [90, "90 days"],
  [180, "6 months"],
] as const

const kj = (j: number) => (j / 1000).toFixed(1)

/** Critical power and W' fitted to the best 3-20 min efforts, with a 95% interval and monthly history (#114). */
export function PowerModel() {
  const [days, setDays] = useState(90)
  const fetcher = useCallback(() => getPowerModel(days), [days])
  const [load, retry] = useLoad<Model>(fetcher)
  return (
    <Panel title="Critical power model" load={load} retry={retry}>
      {(m) => {
        const f = m.fit
        const hist = (m.history ?? []).filter((h) => h.status === "ok" && h.cp_w != null)
        return (
          <div className="space-y-3 text-sm">
            <Label className="flex items-center gap-2 text-sm">
              Best efforts from
              <NativeSelect value={days} onChange={(e) => setDays(Number(e.target.value))}>
                {WINDOWS.map(([d, label]) => (
                  <option key={d} value={d}>
                    {label}
                  </option>
                ))}
              </NativeSelect>
            </Label>
            {f.status !== "ok" || f.cp_w == null || f.wprime_j == null ? (
              <p>No model for this range: {f.reason}</p>
            ) : (
              <>
                <dl className="grid gap-x-6 gap-y-1 sm:grid-cols-2">
                  <Row label="Critical power (CP)" value={`${Math.round(f.cp_w)} W (95%: ${f.cp_ci95_w?.map(Math.round).join("–")})`} />
                  <Row label="W′" value={`${kj(f.wprime_j)} kJ (95%: ${f.wprime_ci95_j?.map(kj).join("–")})`} />
                  <Row label="CP per kg" value={m.cp_w_per_kg != null ? `${m.cp_w_per_kg.toFixed(2)} W/kg` : "—"} />
                  <Row label="Peak power (Pmax)" value={m.pmax_w != null ? `${m.pmax_w} W` : "—"} />
                  <Row label="Fit" value={`${f.n_points} efforts, R² ${f.r2?.toFixed(4)}, error ${f.see_j != null ? kj(f.see_j) : "—"} kJ`} />
                </dl>
                <p className="text-muted-foreground">
                  Efforts used: {f.points.map((p) => `${fmtDuration(p.duration_s)} ${p.watts} W`).join(" · ")}
                </p>
              </>
            )}
            {hist.length >= 2 && (
              <LineChart
                unit="W"
                summary={`Critical power at the end of each of the last ${hist.length} months with enough efforts.`}
                series={[{ name: "CP by month", color: "var(--chart-2)", points: hist.map((h, i) => ({ x: i, y: h.cp_w as number })) }]}
              />
            )}
            <p className="text-xs text-muted-foreground">
              {m.method} {m.caveat}
            </p>
          </div>
        )
      }}
    </Panel>
  )
}
