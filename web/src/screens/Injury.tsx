import { useState } from "react"

import type { InjuryEpisode, InjuryStatus, RampRate } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/native-select"
import { isoDay } from "@/lib/home"
import {
  addEpisode,
  deleteEpisode,
  episodeProblem,
  getInjury,
  getRampRate,
  LEVEL_TEXT,
  rebuildIfNeeded,
  resolveEpisode,
  type EpisodeSport,
  type EpisodeType,
} from "@/lib/injury"
import { Panel, useLoad } from "@/screens/panel"

const SPORTS: [EpisodeSport, string][] = [
  ["all", "All sports"],
  ["cycling", "Cycling"],
  ["running", "Running"],
  ["swimming", "Swimming"],
  ["other", "Other"],
]
const SPORT_NAME = Object.fromEntries(SPORTS) as Record<string, string>

const summary = (e: InjuryEpisode) =>
  `${e.type === "illness" ? "Illness" : "Injury"}${e.body_area ? ` (${e.body_area})` : ""}, ${SPORT_NAME[e.sport] ?? e.sport}: ${e.start} to ${e.end ?? "ongoing"}`

/** Runs a change, rebuilds the plan if its time off moved, then reloads. */
function useChange(onChanged: () => void) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const run = async (fn: () => Promise<InjuryStatus>) => {
    setBusy(true)
    setError("")
    try {
      setError(await rebuildIfNeeded(await fn()))
      onChanged()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }
  return { busy, error, run }
}

function NewEpisodeForm({ onChanged }: { onChanged: () => void }) {
  const [type, setType] = useState<EpisodeType>("illness")
  const [sport, setSport] = useState<EpisodeSport>("all")
  const [start, setStart] = useState(isoDay())
  const [end, setEnd] = useState("")
  const [area, setArea] = useState("")
  const [note, setNote] = useState("")
  const { busy, error, run } = useChange(() => {
    setEnd("")
    setArea("")
    setNote("")
    onChanged()
  })
  const why = episodeProblem({ start, end })
  return (
    <div className="flex flex-wrap items-end gap-2 text-sm">
      <Label className="flex-col items-start gap-1">
        Kind
        <NativeSelect value={type} onChange={(e) => setType(e.target.value as EpisodeType)}>
          <option value="illness">Illness</option>
          <option value="injury">Injury</option>
        </NativeSelect>
      </Label>
      <Label className="flex-col items-start gap-1">
        Sport affected
        <NativeSelect value={sport} onChange={(e) => setSport(e.target.value as EpisodeSport)}>
          {SPORTS.map(([id, label]) => (
            <option key={id} value={id}>
              {label}
            </option>
          ))}
        </NativeSelect>
      </Label>
      <Label className="flex-col items-start gap-1">
        Started
        <Input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
      </Label>
      <Label className="flex-col items-start gap-1">
        Ended (empty if ongoing)
        <Input type="date" min={start} value={end} onChange={(e) => setEnd(e.target.value)} />
      </Label>
      <Label className="flex-col items-start gap-1">
        Body area
        <Input value={area} maxLength={60} onChange={(e) => setArea(e.target.value)} className="max-w-36" />
      </Label>
      <Label className="flex-col items-start gap-1">
        Note
        <Input value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} />
      </Label>
      <Button
        size="sm"
        disabled={busy || !!why}
        onClick={() => run(() => addEpisode({ type, sport, start, end: end || undefined, body_area: area, note }))}
      >
        {busy ? "Saving…" : "Save"}
      </Button>
      {why && <p className="w-full text-muted-foreground">{why}</p>}
      {error && (
        <p role="alert" className="w-full">
          {error}
        </p>
      )}
      <p className="w-full text-xs text-muted-foreground">
        An injury or illness that affects cycling pauses the plan until you mark it over; one that affects only
        another sport is kept for your records and the load warning below.
      </p>
    </div>
  )
}

function Episodes({ data, onChanged }: { data: InjuryStatus; onChanged: () => void }) {
  const [end, setEnd] = useState("")
  const { busy, error, run } = useChange(onChanged)
  const active = data.active
  return (
    <div className="space-y-3 text-sm">
      {active ? (
        <div className="space-y-2">
          <p>Now: {summary(active)}</p>
          {active.note && <p className="text-muted-foreground">{active.note}</p>}
          <div className="flex flex-wrap items-end gap-2">
            {/* "I'm back" ends it yesterday, so it needs a start before today (else: delete it, or pick its last day). */}
            {active.start < isoDay() && (
              <Button size="sm" disabled={busy} onClick={() => run(() => resolveEpisode(active.id))}>
                I'm back
              </Button>
            )}
            <Label className="flex-col items-start gap-1">
              Last day of it
              <Input type="date" min={active.start} value={end} onChange={(e) => setEnd(e.target.value)} />
            </Label>
            <Button size="sm" variant="outline" disabled={busy || !end} onClick={() => run(() => resolveEpisode(active.id, end))}>
              Mark recovered
            </Button>
          </div>
        </div>
      ) : (
        <p className="text-muted-foreground">Nothing ongoing.</p>
      )}
      {data.episodes.length > 0 && (
        <ul className="space-y-1">
          {data.episodes.map((e) => (
            <li key={e.id} className="flex items-center justify-between gap-2">
              <span>{summary(e)}</span>
              <Button size="sm" variant="ghost" disabled={busy} onClick={() => run(() => deleteEpisode(e.id))} aria-label={`Delete ${summary(e)}`}>
                Delete
              </Button>
            </li>
          ))}
        </ul>
      )}
      {error && <p role="alert">{error}</p>}
    </div>
  )
}

function ReturnRamp({ data }: { data: InjuryStatus }) {
  const r = data.return_ramp
  return (
    <div className="space-y-2 text-sm">
      {data.active ? (
        <p>The plan is paused while this goes on. When you feel well, press "I'm back". An injury, or an illness of 15 days or more, then returns through an easy-only ramp; a shorter illness does not.</p>
      ) : r ? (
        <p>
          Back after {r.episode_days} day{r.episode_days === 1 ? "" : "s"} of {r.type}
          {r.weeks_done > 0 ? `, ${r.weeks_done} ramp week${r.weeks_done === 1 ? "" : "s"} done` : ""}.
        </p>
      ) : data.short_break ? (
        <p>
          Back after {data.short_break.episode_days} day{data.short_break.episode_days === 1 ? "" : "s"} of {data.short_break.type}. A short illness has no forced return ramp: train as you feel, and the plan keeps your intensity and trims the volume for a short break.
        </p>
      ) : (
        <p className="text-muted-foreground">No recent episode, so no return ramp.</p>
      )}
      {!data.has_plan && <p className="text-muted-foreground">There is no plan yet: episodes are kept and apply when you make one.</p>}
      {data.ramp_weeks.length > 0 && (
        <table className="w-full">
          <thead>
            <tr className="text-left text-muted-foreground">
              <th className="font-normal">Week from</th>
              <th className="font-normal">Load target</th>
              <th className="font-normal">Riding</th>
            </tr>
          </thead>
          <tbody>
            {data.ramp_weeks.map((w) => (
              <tr key={w.start}>
                <td>{w.start}</td>
                <td>{Math.round(w.tss_target)}</td>
                <td>{w.easy_only ? "Easy only" : "Easy, building"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="text-xs text-muted-foreground">{data.method}</p>
    </div>
  )
}

/** This week's load against the 4 weeks before, combined and per sport. */
export function RampRateCard() {
  const [load, retry] = useLoad<RampRate>(getRampRate)
  return (
    <Panel title="Weekly ramp rate" load={load} retry={retry}>
      {(d) => (
        <div className="space-y-2 text-sm">
          {d.warnings.map((w) => (
            <p key={w} className="font-medium">
              {w}
            </p>
          ))}
          {!d.warn && <p>No sport is ramping faster than {Math.round((d.threshold - 1) * 100)}% above its 4-week average.</p>}
          <table className="w-full">
            <thead>
              <tr className="text-left text-muted-foreground">
                <th className="font-normal">Sport</th>
                <th className="font-normal">7 days</th>
                <th className="font-normal">4-week average</th>
                <th className="font-normal">Change</th>
              </tr>
            </thead>
            <tbody>
              {[["All sports", d.combined] as const, ...Object.entries(d.sports).map(([k, v]) => [SPORT_NAME[k] ?? k, v] as const)].map(([name, l]) => (
                <tr key={name}>
                  <td>{name}</td>
                  <td>{Math.round(l.week_load)}</td>
                  <td>{Math.round(l.prev_4wk_avg)}</td>
                  <td>{l.change_pct == null ? LEVEL_TEXT[l.level] : `${l.change_pct > 0 ? "+" : ""}${l.change_pct}% (${LEVEL_TEXT[l.level] ?? l.level})`}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-xs text-muted-foreground">
            {d.method} {d.confidence}
          </p>
        </div>
      )}
    </Panel>
  )
}

/** Injury and illness: record an episode, mark it over, and see the return ramp and the load warning. */
export function Injury() {
  const [status, retry, refresh] = useLoad<InjuryStatus>(getInjury)
  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">Injury & illness</h1>
      <p role="note" className="rounded-md border p-3 text-sm">
        Not medical advice. This is a conservative training heuristic. See a clinician for an injury that is not
        settling, and do not train with a fever or chest symptoms (chest pain, breathlessness, palpitations).
      </p>
      <Panel title="Record an episode" load={status} retry={retry}>
        {() => <NewEpisodeForm onChanged={refresh} />}
      </Panel>
      <div className="grid gap-4 md:grid-cols-2">
        <Panel title="Episodes" load={status} retry={retry}>
          {(d) => <Episodes data={d} onChanged={refresh} />}
        </Panel>
        <Panel title="Return to training" load={status} retry={retry}>
          {(d) => <ReturnRamp data={d} />}
        </Panel>
      </div>
      <RampRateCard />
    </div>
  )
}
