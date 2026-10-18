import { useCallback, useState } from "react"

import type { WeightTrend as Trend } from "@/api/types"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/native-select"
import { RANGES } from "@/lib/analysis"
import { fmtDelta, getWeightTrend } from "@/lib/analytics"
import { LineChart } from "@/screens/Chart"
import { Panel, Row, useLoad } from "@/screens/panel"

const dayNo = (iso: string) => Date.parse(iso) / 86_400_000

/** Body weight (typed in and synced) with its smoothed trend, and W/kg from your FTP over that trend (#114). */
export function WeightTrend() {
  const [days, setDays] = useState(365)
  const fetcher = useCallback(() => getWeightTrend(days), [days])
  const [load, retry] = useLoad<Trend>(fetcher)
  return (
    <Panel title="Weight and W/kg" load={load} retry={retry}>
      {(t) => {
        const pts = t.points ?? []
        const wkg = t.wkg ?? []
        return (
          <div className="space-y-3 text-sm">
            <Label className="flex items-center gap-2 text-sm">
              Range
              <NativeSelect value={days} onChange={(e) => setDays(Number(e.target.value))}>
                {RANGES.map(([d, label]) => (
                  <option key={d} value={d}>
                    {label}
                  </option>
                ))}
              </NativeSelect>
            </Label>
            {pts.length === 0 ? (
              <p>No weight recorded in this range. Add it in Settings or sync it from intervals.icu.</p>
            ) : (
              <>
                <dl className="grid gap-x-6 gap-y-1 sm:grid-cols-2">
                  <Row label="Trend weight" value={`${t.latest_trend_kg?.toFixed(1)} kg`} />
                  <Row label="Change over 28 days" value={fmtDelta(t.change_28d_kg, " kg", 1)} />
                  <Row label="W/kg (FTP)" value={t.latest_w_per_kg != null ? t.latest_w_per_kg.toFixed(2) : "—"} />
                  <Row label="Readings" value={pts.length} />
                </dl>
                {pts.length >= 2 && (
                  <LineChart
                    unit="kg"
                    summary={`Weight over ${pts.length} readings; trend now ${t.latest_trend_kg?.toFixed(1)} kg.`}
                    series={[
                      { name: "Readings", color: "var(--muted-foreground)", points: pts.map((p) => ({ x: dayNo(p.date), y: p.weight_kg })) },
                      { name: "Trend", color: "var(--chart-2)", points: pts.map((p) => ({ x: dayNo(p.date), y: p.trend_kg })) },
                    ]}
                  />
                )}
                {wkg.length >= 2 && (
                  <LineChart
                    unit="W/kg"
                    summary={`W/kg from FTP over trend weight, ${wkg.length} points, now ${t.latest_w_per_kg?.toFixed(2)}.`}
                    series={[{ name: "FTP W/kg", color: "var(--chart-5)", points: wkg.map((p) => ({ x: dayNo(p.date), y: p.w_per_kg })) }]}
                  />
                )}
                <p className="text-xs text-muted-foreground">{t.method} W/kg is the FTP in force on each date over the trend weight.</p>
              </>
            )}
          </div>
        )
      }}
    </Panel>
  )
}
