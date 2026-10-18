import { useCallback, useState } from "react"

import type { Race, RaceDayPlan, RacesStatus } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/native-select"
import { isoDay } from "@/lib/home"
import {
  countdown,
  createRace,
  DISCIPLINES,
  disciplineText,
  emptyForm,
  EVENT_TYPES,
  fmtHours,
  formOf,
  getRaceDay,
  getRaces,
  isCycling,
  LABEL_NOTE,
  PRIORITY_TEXT,
  raceProblem,
  rebuildIfNeeded,
  removeRace,
  saveRace,
  syncRaces,
  TRI_DISTANCES,
  type Priority,
  type RaceForm,
} from "@/lib/races"
import { Panel, Row, useLoad } from "@/screens/panel"

/** Runs a change, rebuilds the plan if the change reached it, then reloads. */
function useChange(onChanged: () => void) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const run = async (fn: () => Promise<RacesStatus>, after?: () => void) => {
    setBusy(true)
    setError("")
    try {
      setError(await rebuildIfNeeded(await fn()))
      after?.()
      onChanged()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }
  return { busy, error, run }
}

function RaceEditor({ race, onChanged, onCancel }: { race?: Race; onChanged: () => void; onCancel?: () => void }) {
  const [f, setF] = useState<RaceForm>(race ? formOf(race) : emptyForm())
  const { busy, error, run } = useChange(onChanged)
  const set = (k: keyof RaceForm) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })
  const why = raceProblem(f, isoDay(), !race)
  const save = () => run(() => (race ? saveRace(race.id, f) : createRace(f)), race ? onCancel : () => setF(emptyForm()))
  return (
    <div className="flex flex-wrap items-end gap-2 text-sm">
      <Label className="flex-col items-start gap-1">
        Name
        <Input value={f.name} maxLength={80} onChange={set("name")} />
      </Label>
      <Label className="flex-col items-start gap-1">
        Date
        <Input type="date" value={f.date} onChange={set("date")} />
      </Label>
      <Label className="flex-col items-start gap-1">
        Priority
        <NativeSelect value={f.priority} onChange={(e) => setF({ ...f, priority: e.target.value as Priority })}>
          {(["A", "B", "C"] as const).map((p) => (
            <option key={p} value={p}>
              {PRIORITY_TEXT[p]}
            </option>
          ))}
        </NativeSelect>
      </Label>
      <Label className="flex-col items-start gap-1">
        Discipline
        <NativeSelect value={f.discipline} onChange={set("discipline")}>
          {DISCIPLINES.map(([id, label]) => (
            <option key={id} value={id}>
              {label}
            </option>
          ))}
        </NativeSelect>
      </Label>
      {f.discipline === "triathlon" && (
        <Label className="flex-col items-start gap-1">
          Triathlon distance
          <NativeSelect value={f.distance} onChange={set("distance")}>
            <option value="">Pick one</option>
            {TRI_DISTANCES.map(([id, label]) => (
              <option key={id} value={id}>
                {label}
              </option>
            ))}
          </NativeSelect>
        </Label>
      )}
      {isCycling(f.discipline) && (
        <>
          <Label className="flex-col items-start gap-1">
            Type
            <NativeSelect value={f.event_type} onChange={set("event_type")}>
              {EVENT_TYPES.map(([id, label]) => (
                <option key={id} value={id}>
                  {label}
                </option>
              ))}
            </NativeSelect>
          </Label>
          <Label className="flex-col items-start gap-1">
            Distance (km)
            <Input inputMode="decimal" className="max-w-24" value={f.event_km} onChange={set("event_km")} />
          </Label>
          <Label className="flex-col items-start gap-1">
            Climbing (m)
            <Input inputMode="numeric" className="max-w-24" value={f.event_climb_m} onChange={set("event_climb_m")} />
          </Label>
        </>
      )}
      <Label className="flex-col items-start gap-1">
        Your expected duration (h)
        <Input inputMode="decimal" className="max-w-24" value={f.expected_duration_h} onChange={set("expected_duration_h")} />
      </Label>
      <Label className="flex-col items-start gap-1">
        Arrive
        <Input type="time" value={f.arrive_time} onChange={set("arrive_time")} />
      </Label>
      <Label className="flex-col items-start gap-1">
        Start
        <Input type="time" value={f.start_time} onChange={set("start_time")} />
      </Label>
      {!isCycling(f.discipline) && <p className="w-full text-xs text-muted-foreground">{LABEL_NOTE}</p>}
      <Button size="sm" disabled={busy || !!why} onClick={save}>
        {busy ? "Saving…" : race ? "Save race and rebuild plan" : "Add race and rebuild plan"}
      </Button>
      {onCancel && (
        <Button size="sm" variant="ghost" disabled={busy} onClick={onCancel}>
          Cancel
        </Button>
      )}
      {why && f.date && <p className="w-full text-muted-foreground">{why}</p>}
      {error && (
        <p role="alert" className="w-full">
          {error}
        </p>
      )}
    </div>
  )
}

const label = (r: Race) => `${r.priority} race${r.name ? `: ${r.name}` : ""}`
const kind = (r: Race) => (disciplineText(r) ? ` · ${disciplineText(r)}` : "")

function RaceList({ data, onChanged, onRaceDay }: { data: RacesStatus; onChanged: () => void; onRaceDay: (id: string) => void }) {
  const [editing, setEditing] = useState<string | null>(null)
  const { busy, error, run } = useChange(onChanged)
  const missing = data.has_plan && data.races.some((r) => !r.in_plan && r.priority !== "A" && r.days_to_go >= 0)
  if (!data.races.length) return <p className="text-sm text-muted-foreground">No races yet. Add one below.</p>
  return (
    <div className="space-y-3 text-sm">
      <ul className="divide-y">
        {data.races.map((r) => (
          <li key={r.id} className="space-y-1 py-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span>
                <span className="font-medium">{label(r)}</span>
                {kind(r)} · {r.date} · {countdown(r.days_to_go)}
                {r.event_km ? ` · ${r.event_km} km` : ""}
                {r.event_climb_m ? ` / ${r.event_climb_m} m` : ""}
              </span>
              <span className="flex gap-1">
                <Button size="sm" variant="outline" onClick={() => onRaceDay(r.id)} aria-label={`Race day plan for ${label(r)}`}>
                  Race day
                </Button>
                <Button size="sm" variant="ghost" disabled={busy} onClick={() => setEditing(editing === r.id ? null : r.id)} aria-label={`Edit ${label(r)}`}>
                  Edit
                </Button>
                <Button size="sm" variant="ghost" disabled={busy} onClick={() => run(() => removeRace(r.id))} aria-label={`Delete ${label(r)}`}>
                  Delete
                </Button>
              </span>
            </div>
            <p className="text-muted-foreground">{r.taper.text}</p>
            {editing === r.id && <RaceEditor race={r} onChanged={onChanged} onCancel={() => setEditing(null)} />}
          </li>
        ))}
      </ul>
      {missing && (
        <Button size="sm" variant="outline" disabled={busy} onClick={() => run(syncRaces)}>
          Put my races back in the plan
        </Button>
      )}
      {!data.has_plan && <p className="text-muted-foreground">There is no plan yet: build one on the Plan screen and your B and C races go into it on your next change here.</p>}
      {error && <p role="alert">{error}</p>}
    </div>
  )
}

function Tapers({ data }: { data: RacesStatus }) {
  const windows = data.races.filter((r) => r.in_plan && r.taper.start && r.days_to_go >= 0)
  return (
    <div className="space-y-2 text-sm">
      {windows.length === 0 && <p className="text-muted-foreground">No upcoming race in your plan.</p>}
      <ul className="space-y-1">
        {windows.map((r) => (
          <li key={r.id}>
            <span className="font-medium">{label(r)}</span>: {r.taper.start} to {r.taper.end}
            {r.taper.planned_tss != null ? ` · ${Math.round(r.taper.planned_tss)} TSS planned` : ""}
            {r.taper.before_tss != null ? ` (the ${Math.round(r.taper.before_tss)} TSS week before)` : ""}
          </li>
        ))}
      </ul>
      {data.taper_weeks.length > 0 && (
        <table className="w-full">
          <thead>
            <tr className="text-left text-muted-foreground">
              <th className="font-normal">Taper week</th>
              <th className="font-normal">Load target</th>
              <th className="font-normal">Planned</th>
            </tr>
          </thead>
          <tbody>
            {data.taper_weeks.map((w) => (
              <tr key={w.start}>
                <td>
                  {w.start} to {w.end}
                </td>
                <td>{Math.round(w.tss_target)}</td>
                <td>{Math.round(w.planned_tss)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="text-xs text-muted-foreground">
        {data.method} {data.confidence}
      </p>
    </div>
  )
}

function RaceDay({ id }: { id: string }) {
  const fetcher = useCallback(() => getRaceDay(id), [id])
  const [load, retry] = useLoad<RaceDayPlan>(fetcher)
  return (
    <Panel title="Race day plan" load={load} retry={retry}>
      {(d) => {
        const p = d.power
        return (
          <div className="space-y-3 text-sm">
            <p>
              <span className="font-medium">{label(d.race)}</span> · {d.race.date} · {countdown(d.race.days_to_go)}
            </p>
            {d.timeline.length ? (
              <ol className="space-y-0.5">
                {d.timeline.map((t) => (
                  <li key={t.label}>
                    <span className="tabular-nums">{t.time}</span> {t.label}
                  </li>
                ))}
              </ol>
            ) : (
              <p className="text-muted-foreground">
                Add a start time (Edit) to see the day's timeline{d.warmup_min ? `: a ${d.warmup_min} min warm-up before the start` : ""}.
              </p>
            )}
            <dl className="grid gap-x-6 gap-y-1 sm:grid-cols-2">
              {d.expected_duration_h != null && <Row label="Your expected duration" value={fmtHours(d.expected_duration_h)} />}
              {p.available && p.projected_duration_h != null && <Row label="Projected duration" value={fmtHours(p.projected_duration_h)} />}
              {p.available && (
                <Row label="Target power (NP)" value={`${p.np_low}–${p.np_high} W (IF ${p.if_low?.toFixed(2)}–${p.if_high?.toFixed(2)})`} />
              )}
              {p.available && <Row label="Projection's estimate" value={`${p.predicted_np} W, ${Math.round(p.predicted_tss ?? 0)} TSS`} />}
            </dl>
            {!p.available && <p className="text-muted-foreground">{p.reason}</p>}
            {p.available && (
              <p className="text-xs text-muted-foreground">
                {p.method} {p.confidence}
              </p>
            )}
            <p>{d.fueling}</p>
          </div>
        )
      }}
    </Panel>
  )
}

/** Races: the A/B/C list, the taper each gets in the plan, and a race-day plan. */
export function Races() {
  const [status, retry, refresh] = useLoad<RacesStatus>(getRaces)
  const [day, setDay] = useState<string | null>(null)
  const [rev, setRev] = useState(0)
  const changed = () => {
    refresh()
    setRev((n) => n + 1)
  }
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-lg font-semibold">Races</h1>
        <a href="#/plan" className="text-sm underline">
          Back to the plan
        </a>
      </div>
      <Panel title="Your races" load={status} retry={retry}>
        {(d) => <RaceList data={d} onChanged={changed} onRaceDay={setDay} />}
      </Panel>
      <Panel title="Add a race" load={status} retry={retry}>
        {() => <RaceEditor onChanged={changed} />}
      </Panel>
      {day && <RaceDay key={`${day}:${rev}`} id={day} />}
      <Panel title="Tapers in your plan" load={status} retry={retry}>
        {(d) => <Tapers data={d} />}
      </Panel>
    </div>
  )
}
