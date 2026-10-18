import { useCallback, useState } from "react"

import type { FtpTestAnalysis, RideDetail as Ride } from "@/api/types"
import { Button, buttonVariants } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Checkbox } from "@/components/ui/checkbox"
import { Label } from "@/components/ui/label"
import { compareRoute } from "@/lib/analytics"
import { rideInsight } from "@/lib/coach"
import { fmtMinutes } from "@/lib/home"
import { deleteRide, fitUrl, getFtpAnalysis, getRide, isFitRide, reviewFtp, setRace, setRpe, updateFtp, ZONE_NAMES } from "@/lib/rides"
import type { Series } from "@/lib/analysis"
import { averagePace, formatClock, sportKind, type SportKind } from "@/lib/sports"
import { LineChart } from "@/screens/Chart"
import { CoachInsight } from "@/screens/Coach"
import { Panel, Row, useLoad } from "@/screens/panel"

const when = (iso?: string | null) => (iso ? new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "—")
const num = (v: unknown, unit = "", digits = 0) => (typeof v === "number" ? `${digits ? v.toFixed(digits) : Math.round(v)}${unit}` : "—")

const HR_ZONE_NAMES: Record<string, string> = Object.fromEntries([1, 2, 3, 4, 5, 6, 7].map((n) => [`z${n}`, `Zone ${n}`]))

function Zones({ tiz, title = "Time in power zones", names = ZONE_NAMES }: { tiz: Record<string, number>; title?: string; names?: Record<string, string> }) {
  const zones = Object.entries(tiz).filter(([k]) => k in names)
  const total = zones.reduce((n, [, s]) => n + (s || 0), 0)
  if (!total) return null
  return (
    <div className="space-y-1">
      <h3 className="text-xs font-semibold text-muted-foreground">{title}</h3>
      {zones.map(([k, secs]) => (
        <div key={k} className="flex items-center gap-2 text-sm">
          <span className="w-36 text-muted-foreground">{names[k]}</span>
          <span className="h-2 flex-1 rounded-full bg-muted" aria-hidden>
            <span className="block h-2 rounded-full bg-primary" style={{ width: `${(100 * (secs || 0)) / total}%` }} />
          </span>
          <span className="w-16 text-right">{fmtMinutes(Math.round((secs || 0) / 60))}</span>
        </div>
      ))}
    </div>
  )
}

function Traces({ samples, noun }: { samples: Record<string, number[]>; noun: string }) {
  const t = samples.t_s ?? []
  const trace = (key: string, name: string, color: string, unit: string): { s: Series; unit: string } | null => {
    const v = samples[key] ?? []
    if (v.length < 2 || !v.some((x) => x > 0)) return null
    return { s: { name, color, points: v.map((y, i) => ({ x: t[i] ?? i, y })) }, unit }
  }
  const charts = [trace("power_w", "Power", "var(--chart-2)", "W"), trace("hr_bpm", "Heart rate", "var(--chart-5)", "bpm"), trace("elevation_m", "Elevation", "var(--muted-foreground)", "m")].filter(Boolean) as { s: Series; unit: string }[]
  return (
    <div className="space-y-3">
      {charts.map(({ s, unit }) => (
        <LineChart key={s.name} series={[s]} unit={unit} summary={`${s.name} over the ${noun}`} />
      ))}
    </div>
  )
}

function Rpe({ id, initial }: { id: string; initial: number | null }) {
  const [value, setValue] = useState(initial === null ? "" : String(initial))
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState("")
  const [error, setError] = useState("")
  const bad = value !== "" && !(Number(value) >= 0 && Number(value) <= 10)
  const save = async (v: number | null) => {
    setBusy(true)
    setError("")
    setMsg("")
    try {
      await setRpe(id, v)
      if (v === null) setValue("")
      setMsg(v === null ? "Rating cleared." : "Rating saved.")
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="space-y-2 text-sm">
      <Label className="flex-col items-start gap-1">
        How hard was it? (0 to 10)
        <Input type="number" min={0} max={10} step={1} className="w-24" value={value} onChange={(e) => setValue(e.target.value)} />
      </Label>
      <div className="flex gap-2">
        <Button size="sm" disabled={busy || value === "" || bad} onClick={() => save(Math.round(Number(value)))}>
          Save rating
        </Button>
        <Button size="sm" variant="ghost" disabled={busy || initial === null && value === ""} onClick={() => save(null)}>
          Clear
        </Button>
      </div>
      {bad && <p>The rating must be between 0 and 10.</p>}
      {msg && <p role="status">{msg}</p>}
      {error && <p role="alert">Couldn’t save the rating: {error}</p>}
    </div>
  )
}

/** Race-tagged rides weigh more when the app fits your own fitness and fatigue time constants. */
function RaceFlag({ activityId, initial }: { activityId: string; initial: boolean }) {
  const [on, setOn] = useState(initial)
  const [msg, setMsg] = useState("")
  const [error, setError] = useState("")
  const toggle = async (next: boolean) => {
    setError("")
    setMsg("")
    try {
      await setRace(activityId, next)
      setOn(next)
      setMsg(next ? "Marked as a race." : "No longer marked as a race.")
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }
  return (
    <div className="text-sm">
      <Label className="gap-2">
        <Checkbox checked={on} onCheckedChange={(v) => toggle(v === true)} />
        Mark as a race
      </Label>
      {msg && <p role="status">{msg}</p>}
      {error && <p role="alert">Couldn’t save that: {error}</p>}
    </div>
  )
}

/** The FTP test the ride contains: what was scored, and apply, keep or set another value. */
function FtpTest({ id }: { id: string }) {
  const fetcher = useCallback(() => getFtpAnalysis(id), [id])
  const [load, retry] = useLoad<FtpTestAnalysis>(fetcher)
  // A ride that is not a test answers 404; that is not an error worth showing.
  if (load.state === "error" && /no FTP-test|not found/i.test(load.message)) return null
  return (
    <Panel title="FTP test" load={load} retry={retry}>
      {(a) => <FtpVerdict id={id} a={a} />}
    </Panel>
  )
}

function FtpVerdict({ id, a }: { id: string; a: FtpTestAnalysis }) {
  const s = a.suggestion as { ftp?: number; method?: string; type?: string }
  const method = s.method ?? s.type ?? "manual"
  const [custom, setCustom] = useState("")
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState("")
  const [error, setError] = useState("")
  const run = async (work: () => Promise<string>) => {
    setBusy(true)
    setError("")
    try {
      setMsg(await work())
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }
  const suggested = Math.round(s.ftp ?? 0)
  const customBad = custom !== "" && !(Number(custom) >= 50 && Number(custom) <= 600)
  return (
    <div className="space-y-3 text-sm">
      <p>
        {method.replace(/_/g, " ")} test suggests <span className="font-medium">{suggested} W</span>
        {a.prior_ftp ? ` (current FTP ${Math.round(a.prior_ftp)} W)` : ""}.{a.halted ? " The ramp stopped early." : ""}
      </p>
      {a.windows.length > 0 && (
        <ul className="list-disc pl-5 text-muted-foreground">
          {a.windows.map((w, i) => {
            const x = w as { label?: string; start_s?: number; end_s?: number }
            return <li key={i}>{x.label} ({Math.round((x.start_s ?? 0) / 60)} to {Math.round((x.end_s ?? 0) / 60)} min)</li>
          })}
        </ul>
      )}
      <div className="flex flex-wrap items-end gap-2">
        <Button
          size="sm"
          disabled={busy || !suggested}
          onClick={() => run(async () => { const r = await updateFtp(suggested, method, `tested_${method}`, true); await reviewFtp(id, "accepted", suggested); return `FTP is now ${Math.round(r.ftp)} W.` })}
        >
          Use {suggested} W
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={busy || !suggested}
          onClick={() => run(async () => { await updateFtp(suggested, method, "", false); await reviewFtp(id, "declined", suggested); return "Kept your current FTP. The test is logged in your history." })}
        >
          Keep current FTP
        </Button>
        <Label className="flex-col items-start gap-1">
          Another value (W)
          <Input type="number" min={50} max={600} className="w-28" value={custom} onChange={(e) => setCustom(e.target.value)} />
        </Label>
        <Button
          size="sm"
          variant="outline"
          disabled={busy || custom === "" || customBad}
          onClick={() => run(async () => { const v = Math.round(Number(custom)); const r = await updateFtp(v, method, "manual", true); await reviewFtp(id, "edited", v); return `FTP is now ${Math.round(r.ftp)} W.` })}
        >
          Set it
        </Button>
      </div>
      {customBad && <p>FTP must be between 50 and 600 W.</p>}
      {msg && <p role="status">{msg}</p>}
      {error && <p role="alert">Couldn’t update FTP: {error}</p>}
    </div>
  )
}

const NOUN: Record<SportKind, string> = { cycling: "ride", running: "run", swimming: "swim", other: "activity" }

/** The numbers worth showing for this sport. Cycling keeps its power rows; a run or swim shows pace instead. */
function Facts({ r, kind }: { r: Ride; kind: SportKind }) {
  const pace = averagePace(kind, r.moving_s || r.duration_s, r.distance_km)
  const common = (
    <>
      <Row label="Date" value={when(r.started_at)} />
      <Row label="Duration" value={r.duration_s ? fmtMinutes(Math.round(r.duration_s / 60)) : "—"} />
    </>
  )
  const load = <Row label="Load" value={num(r.tss)} />
  const hr = <Row label="Heart rate (avg / max)" value={`${num(r.avg_hr)} / ${num(r.hr_max)}`} />
  if (kind === "running")
    return (
      <>
        {common}
        <Row label="Distance" value={num(r.distance_km, " km", 2)} />
        <Row label="Average pace" value={pace ? `${formatClock(pace)} /km` : "—"} />
        <Row label="Climbing" value={num(r.elevation_m, " m")} />
        {hr}
        {load}
      </>
    )
  if (kind === "swimming")
    return (
      <>
        {common}
        <Row label="Distance" value={typeof r.distance_km === "number" ? `${Math.round(r.distance_km * 1000)} m` : "—"} />
        <Row label="Average pace" value={pace ? `${formatClock(pace)} /100 m` : "—"} />
        {hr}
        {load}
      </>
    )
  if (kind === "other")
    return (
      <>
        {common}
        <Row label="Distance" value={num(r.distance_km, " km", 1)} />
        {hr}
        {load}
      </>
    )
  return (
    <>
      <Row label="Date" value={when(r.started_at)} />
      <Row label="Duration" value={r.duration_s ? fmtMinutes(Math.round(r.duration_s / 60)) : "—"} />
      <Row label="Distance" value={num(r.distance_km, " km", 1)} />
      <Row label="Climbing" value={num(r.elevation_m, " m")} />
      <Row label="Average power" value={num(r.avg_power_w, " W")} />
      <Row label="Normalised power" value={num(r.np_w, " W")} />
      <Row label="Intensity factor" value={num(r.if_pct, "%")} />
      <Row label="Load (TSS)" value={num(r.tss)} />
      <Row label="Work" value={num(r.kj, " kJ")} />
      {hr}
      <Row label="Cadence" value={num(r.avg_cadence, " rpm")} />
      <Row label="Decoupling" value={num(r.decoupling_pct, "%", 1)} />
    </>
  )
}

function Body({ r }: { r: Ride }) {
  const kind = sportKind(r.sport)
  const noun = NOUN[kind]
  const hrTiz = r.hr_time_in_zone as Record<string, number> | null | undefined
  const [confirming, setConfirming] = useState(false)
  const [deleted, setDeleted] = useState(false)
  const [error, setError] = useState("")
  const tiz = r.time_in_zone as Record<string, number> | null | undefined
  const intervals = r.intervals ?? []
  const prs = r.prs ?? []
  const remove = async () => {
    setError("")
    try {
      await deleteRide(r.ride_id)
      setDeleted(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }
  if (deleted) return <p role="status">Ride deleted.</p>
  return (
    <div className="space-y-4">
      <dl className="grid gap-x-6 gap-y-1 sm:grid-cols-2">
        <Facts r={r} kind={kind} />
      </dl>
      {r.samples && <Traces samples={r.samples as Record<string, number[]>} noun={noun} />}
      {kind === "cycling" ? tiz && <Zones tiz={tiz} /> : hrTiz && <Zones tiz={hrTiz} title="Time in heart-rate zones" names={HR_ZONE_NAMES} />}
      {kind === "cycling" && prs.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-muted-foreground">Personal records on this ride</h3>
          <ul className="list-disc pl-5 text-sm">
            {prs.map((p, i) => {
              const x = p as { duration_s?: number; watts?: number; tier?: string }
              return <li key={i}>{x.duration_s ? `${Math.round(x.duration_s / 60) || x.duration_s + " s"}${x.duration_s >= 60 ? " min" : ""}` : "Best"}: {x.watts ?? "?"} W{x.tier ? ` (${x.tier})` : ""}</li>
            })}
          </ul>
        </div>
      )}
      {kind === "cycling" && intervals.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-muted-foreground">Intervals</h3>
          <ul className="divide-y text-sm">
            {intervals.map((iv, i) => {
              const x = iv as { name?: string; start_s?: number; duration_s?: number; avg_power_w?: number; average_watts?: number; ftp_pct?: number }
              const w = x.avg_power_w ?? x.average_watts
              return (
                <li key={i} className="flex justify-between gap-2 py-1">
                  <span>{x.name ?? `Interval ${i + 1}`}</span>
                  <span className="text-muted-foreground">
                    {x.duration_s ? fmtMinutes(Math.round(x.duration_s / 60)) : ""}{w ? ` · ${Math.round(w)} W` : ""}{x.ftp_pct ? ` · ${x.ftp_pct}% FTP` : ""}
                  </span>
                </li>
              )
            })}
          </ul>
        </div>
      )}
      <CoachInsight label={`Review this ${noun}`} run={() => rideInsight(r.ride_id)} />
      <Rpe id={r.ride_id} initial={typeof r.rpe === "number" ? r.rpe : null} />
      {r.activity_id && <RaceFlag activityId={r.activity_id} initial={r.is_race === true} />}
      <div className="flex flex-wrap items-center gap-2">
        <a href={compareRoute(r.ride_id)} className={buttonVariants({ size: "sm", variant: "outline" })}>Compare</a>
        <a href={fitUrl(r.ride_id)} download className={buttonVariants({ size: "sm", variant: "outline" })}>
          Download .fit
        </a>
        {isFitRide(r.ride_id) &&
          (confirming ? (
            <>
              <Button size="sm" variant="destructive" onClick={remove}>
                Yes, delete this ride
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setConfirming(false)}>
                Keep it
              </Button>
            </>
          ) : (
            <Button size="sm" variant="outline" onClick={() => setConfirming(true)}>
              Delete ride…
            </Button>
          ))}
      </div>
      {error && <p role="alert">Couldn’t delete the ride: {error}</p>}
    </div>
  )
}

export function RideDetail({ id }: { id: string }) {
  const fetcher = useCallback(() => getRide(id), [id])
  const [load, retry] = useLoad<Ride>(fetcher)
  const kind = load.state === "ok" ? sportKind(load.data.sport) : "cycling"
  return (
    <div className="space-y-4">
      <a href="#/analysis" className={buttonVariants({ size: "sm", variant: "ghost" })}>
        Back to Analysis
      </a>
      <Panel title={load.state === "ok" ? load.data.name || (kind === "cycling" ? "Ride" : kind === "other" ? "Activity" : kind === "running" ? "Run" : "Swim") : "Ride"} load={load} retry={retry}>
        {(r) => <Body r={r} />}
      </Panel>
      {kind === "cycling" && <FtpTest id={id} />}
    </div>
  )
}

