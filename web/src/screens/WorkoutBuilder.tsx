import { useEffect, useRef, useState } from "react"

import type { BuilderPreview } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/native-select"
import {
  fmtClock,
  KIND_LABEL,
  loadWorkout,
  move,
  newStep,
  preview,
  pushMessage,
  save,
  send,
  startingSteps,
  TARGET_UNIT,
  toWire,
  withUid,
  type Block,
  type Step,
  type Target,
  type TargetKind,
  type UiStep,
} from "@/lib/builder"
import { LineChart } from "@/screens/Chart"

const tomorrow = () => {
  const d = new Date()
  d.setDate(d.getDate() + 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}
const whole = (v: string) => (Number.isFinite(Number(v)) ? Math.max(0, Math.round(Number(v))) : 0)
const errMsg = (e: unknown) => (e instanceof Error ? e.message : String(e))

/** Duration, target and cadence note of one timed block. `who` names it for screen readers ("Step 2", "Step 3 on"). */
function BlockFields({ who, b, onChange }: { who: string; b: Block; onChange: (b: Block) => void }) {
  const unit = TARGET_UNIT[b.target.kind]
  const setTarget = (t: Partial<Target>) => onChange({ ...b, target: { ...b.target, ...t } })
  return (
    <div className="flex flex-wrap items-end gap-2 text-sm">
      <Label className="flex-col items-start gap-1">
        <span aria-hidden>Min</span>
        <Input aria-label={`${who} minutes`} type="number" min={0} className="w-20" value={Math.floor(b.duration_s / 60)} onChange={(e) => onChange({ ...b, duration_s: whole(e.target.value) * 60 + (b.duration_s % 60) })} />
      </Label>
      <Label className="flex-col items-start gap-1">
        <span aria-hidden>Sec</span>
        <Input aria-label={`${who} seconds`} type="number" min={0} max={59} className="w-20" value={b.duration_s % 60} onChange={(e) => onChange({ ...b, duration_s: Math.floor(b.duration_s / 60) * 60 + Math.min(59, whole(e.target.value)) })} />
      </Label>
      <Label className="flex-col items-start gap-1">
        <span aria-hidden>Target</span>
        <NativeSelect aria-label={`${who} target type`} value={b.target.kind} onChange={(e) => setTarget(e.target.value === "hr" ? { kind: "hr" as TargetKind, lo: 70, hi: 80 } : { kind: "power" as TargetKind, lo: 70, hi: 80 })}>
          <option value="power">Power (% FTP)</option>
          <option value="hr">Heart rate (% LTHR)</option>
        </NativeSelect>
      </Label>
      <Label className="flex-col items-start gap-1">
        <span aria-hidden>Low ({unit})</span>
        <Input aria-label={`${who} low (${unit})`} type="number" className="w-24" value={b.target.lo} onChange={(e) => setTarget({ lo: Number(e.target.value) })} />
      </Label>
      <Label className="flex-col items-start gap-1">
        <span aria-hidden>High ({unit})</span>
        <Input aria-label={`${who} high (${unit})`} type="number" className="w-24" value={b.target.hi} onChange={(e) => setTarget({ hi: Number(e.target.value) })} />
      </Label>
      <Label className="min-w-40 flex-1 flex-col items-start gap-1">
        <span aria-hidden>Cadence note</span>
        <Input aria-label={`${who} cadence note`} placeholder="e.g. 90 rpm" maxLength={120} value={b.cadence_note} onChange={(e) => onChange({ ...b, cadence_note: e.target.value })} />
      </Label>
    </div>
  )
}

function StepEditor({ i, n, s, problems, onChange, onMove, onDelete }: {
  i: number
  n: number
  s: UiStep
  problems: string[]
  onChange: (s: UiStep) => void
  onMove: (by: -1 | 1) => void
  onDelete: () => void
}) {
  const who = `Step ${i + 1}`
  const setKind = (kind: Step["kind"]) => {
    // Changing type keeps the timing and target where both kinds have one.
    if (kind === s.kind) return
    const fresh = newStep(kind)
    onChange(s.kind !== "repeat" && kind !== "repeat" ? { ...s, kind } : { ...fresh, uid: s.uid })
  }
  return (
    <li>
      <fieldset className="space-y-2 rounded-lg border p-3">
        <legend className="px-1 text-sm font-medium">{who}: {KIND_LABEL[s.kind]}</legend>
        <div className="flex flex-wrap items-end gap-2 text-sm">
          <Label className="flex-col items-start gap-1">
            <span aria-hidden>Type</span>
            <NativeSelect aria-label={`${who} type`} value={s.kind} onChange={(e) => setKind(e.target.value as Step["kind"])}>
              {(Object.keys(KIND_LABEL) as Step["kind"][]).map((k) => (
                <option key={k} value={k}>{KIND_LABEL[k]}</option>
              ))}
            </NativeSelect>
          </Label>
          {s.kind === "repeat" && (
            <Label className="flex-col items-start gap-1">
              <span aria-hidden>Repeats</span>
              <Input aria-label={`${who} repeats`} type="number" min={1} max={99} className="w-20" value={s.count} onChange={(e) => onChange({ ...s, count: whole(e.target.value) })} />
            </Label>
          )}
          <span className="flex-1" />
          <Button size="sm" variant="outline" aria-label={`Move ${who} up`} disabled={i === 0} onClick={() => onMove(-1)}>Up</Button>
          <Button size="sm" variant="outline" aria-label={`Move ${who} down`} disabled={i === n - 1} onClick={() => onMove(1)}>Down</Button>
          <Button size="sm" variant="destructive" aria-label={`Delete ${who}`} onClick={onDelete}>Delete</Button>
        </div>
        {s.kind === "repeat" ? (
          <>
            <p className="text-xs font-medium text-muted-foreground">Hard part</p>
            <BlockFields who={`${who} on`} b={s.on} onChange={(on) => onChange({ ...s, on })} />
            <p className="text-xs font-medium text-muted-foreground">Easy part</p>
            <BlockFields who={`${who} off`} b={s.off} onChange={(off) => onChange({ ...s, off })} />
          </>
        ) : (
          <BlockFields who={who} b={s} onChange={(b) => onChange({ ...s, ...b })} />
        )}
        {problems.length > 0 && (
          <ul className="text-sm text-destructive">
            {problems.map((p) => <li key={p}>{p}</li>)}
          </ul>
        )}
      </fieldset>
    </li>
  )
}

/** Build a structured cycling workout, see its intensity profile, save it to the Library, and send it to the intervals.icu calendar. */
export function WorkoutBuilder({ file: editing, copy = false }: { file?: string; copy?: boolean }) {
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [steps, setSteps] = useState<UiStep[]>(startingSteps)
  // A copy starts from the loaded model but saves as a new file.
  const [file, setFile] = useState(copy ? undefined : editing)
  const [date, setDate] = useState(tomorrow)
  const [prev, setPrev] = useState<BuilderPreview | null>(null)
  const [prevError, setPrevError] = useState("")
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null)
  const [loadError, setLoadError] = useState("")

  useEffect(() => {
    if (!editing) return
    let live = true
    loadWorkout(editing).then(
      (r) => {
        if (!live) return
        const w = r.workout as { name?: string; description?: string; steps?: Step[] }
        setName(copy ? `${w.name ?? ""} (copy)` : (w.name ?? ""))
        setDescription(w.description ?? "")
        setSteps((w.steps ?? []).map(withUid))
      },
      (e: unknown) => live && setLoadError(errMsg(e)),
    )
    return () => { live = false }
  }, [editing, copy])

  // The preview follows the edits after a short pause; a slower answer to an older edit is dropped.
  const seq = useRef(0)
  useEffect(() => {
    const mine = ++seq.current
    const t = setTimeout(() => {
      preview(toWire(name, description, steps)).then(
        (r) => {
          if (mine !== seq.current) return
          setPrev(r)
          setPrevError("")
        },
        (e: unknown) => mine === seq.current && setPrevError(errMsg(e)),
      )
    }, 300)
    return () => clearTimeout(t)
  }, [name, description, steps])

  const setStep = (i: number, s: UiStep) => setSteps(steps.map((x, j) => (j === i ? s : x)))
  const errors = prev?.errors ?? []
  const forStep = (i: number) => errors.filter((e) => e.path.startsWith(`steps[${i}]`)).map((e) => e.message)
  const general = errors.filter((e) => !/^steps\[\d+\]/.test(e.path))

  const run = async (work: () => Promise<{ ok: boolean; text: string }>) => {
    setBusy(true)
    setStatus(null)
    try {
      setStatus(await work())
    } catch (e) {
      setStatus({ ok: false, text: `Couldn’t do that: ${errMsg(e)}` })
    } finally {
      setBusy(false)
    }
  }
  const onSave = () =>
    run(async () => {
      const r = await save(toWire(name, description, steps), file)
      setFile(r.file)
      return { ok: true, text: `Saved as ${r.file}. It’s in your Workout Library.` }
    })
  const onSend = () =>
    run(async () => {
      const r = await send(toWire(name, description, steps), date, file)
      setFile(r.file)
      const m = pushMessage(r.push, date)
      return { ok: m.ok, text: m.ok ? `Saved as ${r.file}. ${m.text}` : `Saved as ${r.file}, but it wasn’t sent. ${m.text}` }
    })

  const chart = prev?.ok && prev.profile.length > 1
    ? [{ name: "Intensity (% FTP)", color: "var(--primary)", points: prev.profile }]
    : null

  return (
    <div className="grid gap-4 lg:grid-cols-[3fr_2fr]">
      <Card>
        <CardContent className="space-y-3 p-4">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-sm font-semibold">{editing ? "Edit workout" : "New workout"}</h2>
            <Button size="sm" variant="ghost" className="max-md:min-h-11" render={<a href="#/library" />}>Back to the library</Button>
          </div>
          {loadError && <p role="alert" className="text-sm">Couldn’t open that workout: {loadError}</p>}
          <div className="flex flex-wrap gap-2 text-sm">
            <Label className="min-w-48 flex-1 flex-col items-start gap-1">
              Name
              <Input maxLength={80} value={name} onChange={(e) => setName(e.target.value)} />
            </Label>
            <Label className="min-w-48 flex-[2] flex-col items-start gap-1">
              Description (optional)
              <Input maxLength={500} value={description} onChange={(e) => setDescription(e.target.value)} />
            </Label>
          </div>
          <ol className="space-y-3">
            {steps.map((s, i) => (
              <StepEditor key={s.uid} i={i} n={steps.length} s={s} problems={forStep(i)} onChange={(x) => setStep(i, x)} onMove={(by) => setSteps(move(steps, i, by))} onDelete={() => setSteps(steps.filter((_, j) => j !== i))} />
            ))}
          </ol>
          {steps.length === 0 && <p className="text-sm text-muted-foreground">No steps yet. Add one below.</p>}
          <div role="group" aria-label="Add a step" className="flex flex-wrap gap-2">
            {(Object.keys(KIND_LABEL) as Step["kind"][]).map((k) => (
              <Button key={k} size="sm" variant="outline" onClick={() => setSteps([...steps, newStep(k)])}>
                Add {KIND_LABEL[k].toLowerCase()}
              </Button>
            ))}
          </div>
        </CardContent>
      </Card>

      <div className="space-y-4">
        <Card>
          <CardContent className="space-y-2 p-4">
            <h2 className="text-sm font-semibold">Preview</h2>
            {prevError && <p role="alert" className="text-sm">Couldn’t update the preview: {prevError}</p>}
            {general.length > 0 && (
              <ul className="text-sm text-destructive">
                {general.map((e) => <li key={e.message}>{e.message}</li>)}
              </ul>
            )}
            {chart && <LineChart series={chart} summary={`Intensity profile, ${fmtClock(prev?.duration_s ?? 0)} long`} unit="% FTP" />}
            <p className="text-sm" aria-live="polite">
              {prev?.ok
                ? `${fmtClock(prev.duration_s)} · IF ${prev.intensity_factor ?? "n/a"} · TSS ${prev.tss ?? "n/a"}`
                : errors.length > 0 ? "Fix the problems above to see the numbers." : "Working it out…"}
            </p>
            {(prev?.warnings ?? []).map((w) => <p key={w} className="text-xs text-muted-foreground">{w}</p>)}
            <p className="text-xs text-muted-foreground">Heart-rate steps are written to the file as the power that matches them, so your head unit can show either.</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="space-y-3 p-4">
            <h2 className="text-sm font-semibold">Keep it</h2>
            <div className="flex flex-wrap items-end gap-2 text-sm">
              <Button disabled={busy || !prev?.ok} onClick={onSave}>Save to library</Button>
              <Label className="flex-col items-start gap-1">
                Calendar date
                <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
              </Label>
              <Button variant="outline" disabled={busy || !prev?.ok || !date} onClick={onSend}>Send to calendar</Button>
            </div>
            {status && (
              <p role={status.ok ? "status" : "alert"} className="text-sm">{status.text}</p>
            )}
            <p className="text-xs text-muted-foreground">Sending saves the workout first, then puts it on your intervals.icu calendar, which passes it on to Garmin.</p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
