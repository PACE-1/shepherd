import { useState } from "react"

import type { OpenWaterNote, OpenWaterNotes as Notes } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/native-select"
import { addOpenWaterNote, deleteOpenWaterNote, editOpenWaterNote, getOpenWaterNotes, parseTemp, type NoteFields } from "@/lib/swim"
import { Panel, useLoad } from "@/screens/panel"

export type SwimChoice = { id: string; date?: string | null; name?: string }

const today = () => new Date().toISOString().slice(0, 10)
const blank = (): Form => ({ date: today(), activity_id: "", temp: "", wetsuit: "", conditions: "", course: "", sighting: "", note: "" })
type Form = { date: string; activity_id: string; temp: string; wetsuit: "" | "yes" | "no"; conditions: string; course: string; sighting: string; note: string }

const toForm = (n: OpenWaterNote): Form => ({
  date: n.date, activity_id: n.activity_id ?? "", temp: n.water_temp_c == null ? "" : String(n.water_temp_c),
  wetsuit: n.wetsuit == null ? "" : n.wetsuit ? "yes" : "no",
  conditions: n.conditions ?? "", course: n.course ?? "", sighting: n.sighting ?? "", note: n.note ?? "",
})

function NoteForm({ initial, swims, onSave, onCancel }: { initial: Form; swims: SwimChoice[]; onSave: (f: NoteFields) => Promise<void>; onCancel?: () => void }) {
  const [f, setF] = useState(initial)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const set = <K extends keyof Form>(k: K, v: Form[K]) => setF((x) => ({ ...x, [k]: v }))
  const pickSwim = (id: string) => {
    const s = swims.find((x) => x.id === id)
    setF((x) => ({ ...x, activity_id: id, date: s?.date ?? x.date }))
  }
  const save = async () => {
    setError("")
    const temp = parseTemp(f.temp)
    if (!/^\d{4}-\d{2}-\d{2}$/.test(f.date)) return setError("Pick a date.")
    if (temp === undefined) return setError("Enter the water temperature as a number in °C, like 16.5, or leave it empty.")
    setBusy(true)
    try {
      await onSave({
        date: f.date, activity_id: f.activity_id || null, water_temp_c: temp,
        wetsuit: f.wetsuit === "" ? null : f.wetsuit === "yes",
        conditions: f.conditions, course: f.course, sighting: f.sighting, note: f.note,
      })
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="flex flex-wrap items-end gap-3 text-sm">
      <Label className="flex-col items-start gap-1">
        Date
        <Input type="date" value={f.date} onChange={(e) => set("date", e.target.value)} />
      </Label>
      {swims.length > 0 && (
        <Label className="flex-col items-start gap-1">
          Swim (optional)
          <NativeSelect aria-label="Swim (optional)" value={f.activity_id} onChange={(e) => pickSwim(e.target.value)}>
            <option value="">Not linked</option>
            {swims.map((s) => <option key={s.id} value={s.id}>{s.date} {s.name}</option>)}
          </NativeSelect>
        </Label>
      )}
      <Label className="flex-col items-start gap-1">
        Water temperature (°C)
        <Input value={f.temp} onChange={(e) => set("temp", e.target.value)} className="max-w-24" inputMode="decimal" />
      </Label>
      <Label className="flex-col items-start gap-1">
        Wetsuit
        <NativeSelect aria-label="Wetsuit" value={f.wetsuit} onChange={(e) => set("wetsuit", e.target.value as Form["wetsuit"])}>
          <option value="">Not noted</option>
          <option value="yes">Yes</option>
          <option value="no">No</option>
        </NativeSelect>
      </Label>
      <Label className="flex-col items-start gap-1">
        Conditions
        <Input value={f.conditions} maxLength={200} onChange={(e) => set("conditions", e.target.value)} />
      </Label>
      <Label className="flex-col items-start gap-1">
        Course
        <Input value={f.course} maxLength={200} onChange={(e) => set("course", e.target.value)} />
      </Label>
      <Label className="flex-col items-start gap-1">
        Sighting and navigation
        <Input value={f.sighting} maxLength={500} onChange={(e) => set("sighting", e.target.value)} />
      </Label>
      <Label className="w-full flex-col items-start gap-1">
        Notes
        <textarea
          value={f.note}
          maxLength={1000}
          rows={2}
          onChange={(e) => set("note", e.target.value)}
          className="w-full rounded-lg border border-input bg-background px-3 py-1 text-sm dark:bg-input/30"
        />
      </Label>
      <div className="flex gap-2">
        <Button size="sm" disabled={busy} onClick={save}>{busy ? "Saving…" : "Save note"}</Button>
        {onCancel && <Button size="sm" variant="outline" onClick={onCancel}>Cancel</Button>}
      </div>
      {error && <p role="alert" className="w-full">{error}</p>}
    </div>
  )
}

function summary(n: OpenWaterNote): string {
  const bits = [
    n.water_temp_c != null ? `${n.water_temp_c} °C` : "",
    n.wetsuit == null ? "" : n.wetsuit ? "wetsuit" : "no wetsuit",
    n.conditions ?? "",
    n.course ?? "",
  ].filter(Boolean)
  return bits.join(" · ")
}

function NoteList({ data, swims, refresh }: { data: Notes; swims: SwimChoice[]; refresh: () => void }) {
  const [editing, setEditing] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState("")
  const name = (id?: string | null) => (id ? swims.find((s) => s.id === id)?.name || `activity ${id}` : "")
  const remove = async (id: string) => {
    setError("")
    try {
      await deleteOpenWaterNote(id)
      refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }
  return (
    <div className="space-y-3 text-sm">
      {data.notes?.length ? (
        <ul className="space-y-2" aria-label="Open-water notes">
          {data.notes.map((n) => (
            <li key={n.id} className="space-y-1 border-b pb-2 last:border-0">
              {editing === n.id ? (
                <NoteForm
                  initial={toForm(n)}
                  swims={swims}
                  onCancel={() => setEditing(null)}
                  onSave={async (f) => {
                    await editOpenWaterNote(n.id, f)
                    setEditing(null)
                    refresh()
                  }}
                />
              ) : (
                <>
                  <p className="font-medium">{[n.date, name(n.activity_id), summary(n)].filter(Boolean).join(" · ")}</p>
                  {n.sighting && <p>Sighting: {n.sighting}</p>}
                  {n.note && <p className="whitespace-pre-wrap">{n.note}</p>}
                  <div className="flex gap-2">
                    <Button size="sm" variant="outline" onClick={() => setEditing(n.id)} aria-label={`Edit note of ${n.date}`}>Edit</Button>
                    <Button size="sm" variant="outline" onClick={() => remove(n.id)} aria-label={`Delete note of ${n.date}`}>Delete</Button>
                  </div>
                </>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p>No open-water notes yet.</p>
      )}
      {adding ? (
        <NoteForm
          initial={blank()}
          swims={swims}
          onCancel={() => setAdding(false)}
          onSave={async (f) => {
            await addOpenWaterNote(f)
            setAdding(false)
            refresh()
          }}
        />
      ) : (
        <Button size="sm" onClick={() => setAdding(true)}>Add a note</Button>
      )}
      {error && <p role="alert">{error}</p>}
      <p className="text-xs text-muted-foreground">Your own notes on open-water swims, kept on this computer in your profile. Shepherd does not work anything out from them.</p>
    </div>
  )
}

/** Open-water and wetsuit notes (#126): a plain record per swim, listed and editable. */
export function OpenWaterNotes({ swims = [] }: { swims?: SwimChoice[] }) {
  const [notes, retry, refresh] = useLoad<Notes>(getOpenWaterNotes)
  return (
    <Panel title="Open-water notes" load={notes} retry={retry}>
      {(d) => <NoteList data={d} swims={swims} refresh={refresh} />}
    </Panel>
  )
}
