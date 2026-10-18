import { useCallback, useState, type ReactNode } from "react"

import type { RideCompare as Comparison, RideSummary } from "@/api/types"
import { Button, buttonVariants } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/native-select"
import { fmtDuration, getRides } from "@/lib/analysis"
import { binnedPoints, compareRides, compareRoute, effortFromMinutes, fmtClock, fmtDelta, type Effort } from "@/lib/analytics"
import { rideRoute } from "@/lib/rides"
import { LineChart } from "@/screens/Chart"
import { Panel, useLoad } from "@/screens/panel"

type Summary = Comparison["a"]["summary"]
type Key = keyof Summary

const ROWS: { key: Key; label: string; fmt: (v: number) => string; delta: (v: number | null | undefined) => string }[] = [
  { key: "duration_s", label: "Duration", fmt: fmtClock, delta: (v) => (v == null ? "—" : `${v < 0 ? "−" : "+"}${fmtClock(Math.abs(v))}`) },
  { key: "distance_km", label: "Distance", fmt: (v) => `${v.toFixed(1)} km`, delta: (v) => fmtDelta(v, " km", 1) },
  { key: "np_w", label: "Normalised power", fmt: (v) => `${Math.round(v)} W`, delta: (v) => fmtDelta(v, " W") },
  { key: "if_pct", label: "Intensity factor", fmt: (v) => `${Math.round(v)}%`, delta: (v) => fmtDelta(v, "%") },
  { key: "tss", label: "Load (TSS)", fmt: (v) => String(Math.round(v)), delta: (v) => fmtDelta(v) },
  { key: "avg_hr", label: "Average heart rate", fmt: (v) => `${Math.round(v)} bpm`, delta: (v) => fmtDelta(v, " bpm") },
]

const day = (iso?: string | null) => (iso ? new Date(iso).toLocaleDateString(undefined, { dateStyle: "medium" }) : "")
const show = (s: Summary, k: Key, fmt: (v: number) => string) => (typeof s[k] === "number" ? fmt(s[k] as number) : "—")

function Cell({ children, head }: { children: ReactNode; head?: boolean }) {
  return head ? <th scope="row" className="py-1 pr-3 text-left font-normal text-muted-foreground">{children}</th> : <td className="py-1 pr-3 text-right">{children}</td>
}

function Result({ c }: { c: Comparison }) {
  const pa = binnedPoints(c.a.power_w ?? [], c.bin_s)
  const pb = binnedPoints(c.b.power_w ?? [], c.bin_s)
  const ha = binnedPoints(c.a.hr_bpm ?? [], c.bin_s)
  const hb = binnedPoints(c.b.hr_bpm ?? [], c.bin_s)
  const label = (s: Comparison["a"], tag: string) => `${tag}: ${s.name}${!s.whole ? ` (${fmtClock(s.start_s)}–${fmtClock(s.end_s)})` : ""}`
  return (
    <div className="space-y-4 text-sm">
      <table className="w-full">
        <caption className="sr-only">Summary of both, and B minus A</caption>
        <thead>
          <tr className="text-xs text-muted-foreground">
            <th scope="col" />
            <th scope="col" className="pr-3 text-right font-medium">A</th>
            <th scope="col" className="pr-3 text-right font-medium">B</th>
            <th scope="col" className="pr-3 text-right font-medium">B − A</th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map((r) => (
            <tr key={r.key} className="border-t">
              <Cell head>{r.label}</Cell>
              <Cell>{show(c.a.summary, r.key, r.fmt)}</Cell>
              <Cell>{show(c.b.summary, r.key, r.fmt)}</Cell>
              <Cell>{r.delta(c.delta[r.key] as number | null | undefined)}</Cell>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-muted-foreground">
        {label(c.a, "A")} · {label(c.b, "B")}. Curves are aligned by elapsed time from each start, averaged over {c.bin_s} s.
      </p>
      {(pa.length > 1 || pb.length > 1) && (
        <LineChart unit="W" summary="Power of A and B by elapsed minutes" series={[{ name: "A power", color: "var(--chart-2)", points: pa }, { name: "B power", color: "var(--chart-5)", points: pb }]} />
      )}
      {(ha.length > 1 || hb.length > 1) && (
        <LineChart unit="bpm" summary="Heart rate of A and B by elapsed minutes" series={[{ name: "A heart rate", color: "var(--chart-2)", points: ha }, { name: "B heart rate", color: "var(--chart-5)", points: hb }]} />
      )}
      {c.best_efforts.length > 0 && (
        <table className="w-full">
          <caption className="text-left text-xs font-semibold text-muted-foreground">Best efforts</caption>
          <thead>
            <tr className="text-xs text-muted-foreground">
              <th scope="col" />
              <th scope="col" className="pr-3 text-right font-medium">A</th>
              <th scope="col" className="pr-3 text-right font-medium">B</th>
              <th scope="col" className="pr-3 text-right font-medium">B − A</th>
            </tr>
          </thead>
          <tbody>
            {c.best_efforts.map((e) => (
              <tr key={e.duration_s} className="border-t">
                <Cell head>{fmtDuration(e.duration_s)}</Cell>
                <Cell>{e.a_w} W</Cell>
                <Cell>{e.b_w} W</Cell>
                <Cell>{fmtDelta(e.delta_w, " W")}</Cell>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function Compared({ a, b, ea, eb }: { a: string; b: string; ea: Effort; eb: Effort }) {
  const fetcher = useCallback(() => compareRides(a, b, ea, eb), [a, b, ea, eb])
  const [load, retry] = useLoad<Comparison>(fetcher)
  return (
    <Panel title="Side by side" load={load} retry={retry}>
      {(c) => <Result c={c} />}
    </Panel>
  )
}

function EffortInputs({ tag, start, end, onStart, onEnd }: { tag: string; start: string; end: string; onStart: (v: string) => void; onEnd: (v: string) => void }) {
  return (
    <fieldset className="flex flex-wrap items-end gap-2">
      <legend className="text-xs text-muted-foreground">{tag}: effort (minutes from the start; leave empty for the whole ride)</legend>
      <Label className="flex items-center gap-1 text-sm">
        From
        <Input className="w-20" inputMode="decimal" value={start} onChange={(e) => onStart(e.target.value)} />
      </Label>
      <Label className="flex items-center gap-1 text-sm">
        to
        <Input className="w-20" inputMode="decimal" value={end} onChange={(e) => onEnd(e.target.value)} />
      </Label>
    </fieldset>
  )
}

/** Two rides, or two efforts of rides, side by side (#116). `a` comes from the ride it was opened from. */
export function RideCompare({ a, b: initialB }: { a: string; b?: string }) {
  const ridesFetcher = useCallback(() => getRides(50), [])
  const [rides, retryRides] = useLoad<RideSummary[]>(ridesFetcher)
  const [b, setB] = useState(initialB ?? "")
  const [as, setAs] = useState("")
  const [ae, setAe] = useState("")
  const [bs, setBs] = useState("")
  const [be, setBe] = useState("")
  const [applied, setApplied] = useState<{ b: string; ea: Effort; eb: Effort } | null>(initialB ? { b: initialB, ea: {}, eb: {} } : null)
  const ea = effortFromMinutes(as, ae)
  const eb = effortFromMinutes(bs, be)
  const go = () => {
    if (!b || !ea || !eb) return
    setApplied({ b, ea, eb })
    window.history.replaceState(null, "", compareRoute(a, b))
  }
  return (
    <div className="space-y-4">
      <a href={rideRoute(a)} className={buttonVariants({ size: "sm", variant: "ghost" })}>
        Back to the ride
      </a>
      <Panel title="Compare rides" load={rides} retry={retryRides}>
        {(list) => {
          const nameOf = (id: string) => {
            const r = list.find((x) => x.ride_id === id)
            return r ? `${day(r.started_at)} · ${r.name || "Ride"}` : id
          }
          return (
            <div className="space-y-3 text-sm">
              <p>A: {nameOf(a)}</p>
              <Label className="flex flex-wrap items-center gap-2 text-sm">
                B
                <NativeSelect value={b} onChange={(e) => setB(e.target.value)}>
                  <option value="">Choose a ride…</option>
                  {b && !list.some((r) => r.ride_id === b) && <option value={b}>{b}</option>}
                  {list
                    .filter((r) => r.ride_id !== a)
                    .map((r) => (
                      <option key={r.ride_id} value={r.ride_id}>
                        {nameOf(r.ride_id)}
                      </option>
                    ))}
                </NativeSelect>
              </Label>
              <EffortInputs tag="A" start={as} end={ae} onStart={setAs} onEnd={setAe} />
              <EffortInputs tag="B" start={bs} end={be} onStart={setBs} onEnd={setBe} />
              {(!ea || !eb) && <p role="alert">An effort must end after it starts.</p>}
              <Button size="sm" onClick={go} disabled={!b || !ea || !eb}>
                Compare
              </Button>
            </div>
          )
        }}
      </Panel>
      {applied && <Compared a={a} b={applied.b} ea={applied.ea} eb={applied.eb} />}
    </div>
  )
}
