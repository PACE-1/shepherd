import { useState } from "react"

import type { GearItem, GearOverview } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/native-select"
import {
  addGear,
  assignRide,
  deleteGear,
  editGear,
  emptyForm,
  formOf,
  formProblem,
  getGear,
  needsAttention,
  progress,
  retireGear,
  serviceDone,
  STATE_TEXT,
  type GearForm,
  type GearKind,
} from "@/lib/gear"
import { isoDay } from "@/lib/home"
import { Panel, useLoad } from "@/screens/panel"

/** Runs a change, then reloads. */
function useChange(onChanged: () => void) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    setError("")
    try {
      await fn()
      onChanged()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }
  return { busy, error, run }
}

function Due({ items }: { items: GearItem[] }) {
  const due = needsAttention(items)
  if (!due.length) return null
  return (
    <div role="status" className="space-y-1 rounded-md border p-3 text-sm">
      {due.map((i) => (
        <p key={i.id}>
          <span className="font-medium">{i.name}</span>: {i.state === "due" ? "service is due" : "service is due soon"}, {progress(i.km, i.service_every_km, "km", i.km_pct)}
          {i.service_every_hours ? `, ${progress(i.hours, i.service_every_hours, "h", i.hours_pct)}` : ""}.
        </p>
      ))}
      <p className="text-xs text-muted-foreground">Gear reminders show here only; Shepherd does not send them as notifications.</p>
    </div>
  )
}

function ItemRow({ item, parent, onEdit, onChanged }: { item: GearItem; parent?: string; onEdit: () => void; onChanged: () => void }) {
  const [day, setDay] = useState(isoDay())
  const { busy, error, run } = useChange(onChanged)
  return (
    <tr className="align-top">
      <td className="py-1 pr-2">
        {item.name}
        <div className="text-xs text-muted-foreground">
          {item.kind}
          {parent ? ` on ${parent}` : ""}
          {item.last_service ? `, serviced ${item.last_service}` : ""}
        </div>
        {error && <p role="alert" className="text-xs">{error}</p>}
      </td>
      <td className="pr-2">{progress(item.km, item.service_every_km, "km", item.km_pct)}</td>
      <td className="pr-2">{progress(item.hours, item.service_every_hours, "h", item.hours_pct)}</td>
      <td className="pr-2">{STATE_TEXT[item.state] ?? item.state}</td>
      <td className="space-x-1 whitespace-nowrap">
        <Input type="date" aria-label={`Service date for ${item.name}`} className="inline-block w-36" max={isoDay()} value={day} onChange={(e) => setDay(e.target.value)} />
        <Button size="sm" disabled={busy || !day} onClick={() => run(() => serviceDone(item.id, day))} aria-label={`Service done for ${item.name}`}>
          Service done
        </Button>
        <Button size="sm" variant="outline" onClick={onEdit} aria-label={`Edit ${item.name}`}>
          Edit
        </Button>
        <Button size="sm" variant="outline" disabled={busy} onClick={() => run(() => retireGear(item.id, !item.retired))} aria-label={`${item.retired ? "Unretire" : "Retire"} ${item.name}`}>
          {item.retired ? "Unretire" : "Retire"}
        </Button>
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => run(() => deleteGear(item.id))} aria-label={`Delete ${item.name}`}>
          Delete
        </Button>
      </td>
    </tr>
  )
}

function Items({ data, onEdit, onChanged }: { data: GearOverview; onEdit: (i: GearItem) => void; onChanged: () => void }) {
  if (!data.items.length) return <p className="text-sm text-muted-foreground">No gear yet. Add a bike, shoes or a component below.</p>
  const name = (id?: string | null) => data.items.find((i) => i.id === id)?.name
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm" aria-label="Gear">
        <thead>
          <tr className="text-left text-muted-foreground">
            <th className="font-normal">Item</th>
            <th className="font-normal">Distance</th>
            <th className="font-normal">Time</th>
            <th className="font-normal">Status</th>
            <th className="font-normal">Actions</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((i) => (
            <ItemRow key={i.id} item={i} parent={name(i.parent_id)} onEdit={() => onEdit(i)} onChanged={onChanged} />
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-muted-foreground">{data.method}</p>
    </div>
  )
}

function GearFormCard({ data, form, setForm, editingId, done }: { data: GearOverview; form: GearForm; setForm: (f: GearForm) => void; editingId: string; done: () => void }) {
  const { busy, error, run } = useChange(done)
  const why = formProblem(form)
  const bikes = data.items.filter((i) => i.kind === "bike" && i.id !== editingId)
  const up = (p: Partial<GearForm>) => setForm({ ...form, ...p })
  return (
    <div className="space-y-2 text-sm">
      {!editingId && data.suggestions.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-muted-foreground">Gear on your intervals.icu rides:</span>
          {data.suggestions.map((s) => (
            <Button key={s.icu_name} size="sm" variant="outline" onClick={() => up({ name: s.icu_name, icu_name: s.icu_name })}>
              Use {s.icu_name} ({s.rides} {s.rides === 1 ? "ride" : "rides"})
            </Button>
          ))}
        </div>
      )}
      <div className="flex flex-wrap items-end gap-2">
        <Label className="flex-col items-start gap-1">
          Name
          <Input value={form.name} maxLength={80} onChange={(e) => up({ name: e.target.value })} />
        </Label>
        <Label className="flex-col items-start gap-1">
          Kind
          <NativeSelect value={form.kind} onChange={(e) => up({ kind: e.target.value as GearKind })}>
            <option value="bike">Bike</option>
            <option value="shoes">Shoes</option>
            <option value="component">Component</option>
          </NativeSelect>
        </Label>
        {form.kind === "component" && (
          <Label className="flex-col items-start gap-1">
            On bike
            <NativeSelect value={form.parent_id} onChange={(e) => up({ parent_id: e.target.value })}>
              <option value="">No bike</option>
              {bikes.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </NativeSelect>
          </Label>
        )}
        <Label className="flex-col items-start gap-1">
          Started on
          <Input type="date" value={form.started_on} onChange={(e) => up({ started_on: e.target.value })} />
        </Label>
        <Label className="flex-col items-start gap-1">
          Service every (km)
          <Input inputMode="decimal" className="w-28" value={form.service_every_km} onChange={(e) => up({ service_every_km: e.target.value })} />
        </Label>
        <Label className="flex-col items-start gap-1">
          Service every (hours)
          <Input inputMode="decimal" className="w-28" value={form.service_every_hours} onChange={(e) => up({ service_every_hours: e.target.value })} />
        </Label>
        {form.kind !== "component" && (
          <Label className="flex-col items-start gap-1">
            intervals.icu gear name
            <Input value={form.icu_name} maxLength={80} onChange={(e) => up({ icu_name: e.target.value })} />
          </Label>
        )}
        <Button size="sm" disabled={busy || !!why} onClick={() => run(() => (editingId ? editGear(editingId, form) : addGear(form)))}>
          {editingId ? "Save changes" : "Add gear"}
        </Button>
        {editingId && (
          <Button size="sm" variant="outline" onClick={done}>
            Cancel
          </Button>
        )}
      </div>
      {why && form.name !== "" && <p className="text-muted-foreground">{why}</p>}
      {error && <p role="alert">{error}</p>}
      <p className="text-xs text-muted-foreground">
        Thresholds are yours: leave them empty and nothing is flagged. A component counts the rides of its bike. Rides pick up
        their gear from intervals.icu when its gear name matches the name above; that match is best-effort.
      </p>
    </div>
  )
}

function Rides({ data, onChanged }: { data: GearOverview; onChanged: () => void }) {
  const { busy, error, run } = useChange(onChanged)
  const choices = data.items.filter((i) => i.kind !== "component")
  if (!data.recent.length) return <p className="text-sm text-muted-foreground">No synced rides yet.</p>
  return (
    <div className="space-y-2">
      <table className="w-full text-sm" aria-label="Recent rides">
        <thead>
          <tr className="text-left text-muted-foreground">
            <th className="font-normal">Date</th>
            <th className="font-normal">Ride</th>
            <th className="font-normal">km</th>
            <th className="font-normal">Gear</th>
          </tr>
        </thead>
        <tbody>
          {data.recent.map((r) => (
            <tr key={r.id}>
              <td>{r.date}</td>
              <td>{r.name}</td>
              <td>{r.distance_km == null ? "" : Math.round(r.distance_km * 10) / 10}</td>
              <td>
                <NativeSelect
                  aria-label={`Gear for ${r.date} ${r.name ?? r.id}`}
                  disabled={busy}
                  value={r.source === "manual" ? (r.gear_id ?? "none") : "auto"}
                  onChange={(e) => run(() => assignRide(r.id, e.target.value === "auto" ? null : e.target.value))}
                >
                  <option value="auto">
                    Automatic{r.source === "auto" ? ` (${data.items.find((i) => i.id === r.gear_id)?.name ?? "?"})` : " (none)"}
                  </option>
                  <option value="none">No gear</option>
                  {choices.map((i) => (
                    <option key={i.id} value={i.id}>
                      {i.name}
                    </option>
                  ))}
                </NativeSelect>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {error && <p role="alert">{error}</p>}
    </div>
  )
}

/** #/gear: bikes, shoes and components with distance and hours, the rider's service thresholds, and "service done" (#115). */
export function Gear() {
  const [data, retry, refresh] = useLoad<GearOverview>(getGear)
  const [form, setForm] = useState<GearForm>(emptyForm)
  const [editingId, setEditingId] = useState("")
  const reset = () => {
    setForm(emptyForm())
    setEditingId("")
    refresh()
  }
  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">Gear</h1>
      {data.state === "ok" && <Due items={data.data.items} />}
      <Panel title="Your gear" load={data} retry={retry}>
        {(d) => (
          <Items
            data={d}
            onChanged={refresh}
            onEdit={(i) => {
              setForm(formOf(i))
              setEditingId(i.id)
            }}
          />
        )}
      </Panel>
      <Panel title={editingId ? "Edit gear" : "Add gear"} load={data} retry={retry}>
        {(d) => <GearFormCard data={d} form={form} setForm={setForm} editingId={editingId} done={reset} />}
      </Panel>
      <Panel title="Recent rides" load={data} retry={retry}>
        {(d) => <Rides data={d} onChanged={refresh} />}
      </Panel>
    </div>
  )
}
