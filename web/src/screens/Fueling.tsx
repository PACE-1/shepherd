import { useState } from "react"

import type { Fueling as FuelingData } from "@/api/types"
import { Button } from "@/components/ui/button"
import { fmtMinutes } from "@/lib/home"
import { carbStatus, getFueling, range, syncNutrition } from "@/lib/nutrition"
import { Panel, Row, useLoad } from "@/screens/panel"

const LOAD: Record<string, string> = { light: "Light day", moderate: "Moderate day (about 1 h)", high: "High day (1 to 3 h)", very_high: "Very high day (4 h or more)" }
const round = (v: number | null | undefined, unit: string) => (v == null ? "—" : `${Math.round(v)} ${unit}`)

function Body({ f, onSynced }: { f: FuelingData; onSynced: () => void }) {
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState("")
  const sync = async () => {
    setBusy(true)
    setMsg("")
    try {
      await syncNutrition()
      onSynced()
    } catch (e) {
      setMsg(`Couldn’t sync: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setBusy(false)
    }
  }
  const { session, during, day, logged } = f
  return (
    <div className="space-y-3 text-sm">
      <section aria-label="During the session" className="space-y-1">
        <h3 className="font-medium">During today’s session</h3>
        {session && during ? (
          <>
            <p>
              Planned: {session.session_type.replace(/_/g, " ")}, {fmtMinutes(session.duration_min)}.
            </p>
            <p>
              {during.note}
              {during.high_g > 0 && ` About ${range(during.low_g, during.high_g, "g")} over the session.`}
            </p>
          </>
        ) : (
          <p>No session planned today.</p>
        )}
      </section>
      <section aria-label="Today's carbohydrate" className="space-y-1">
        <h3 className="font-medium">Carbohydrate for the day</h3>
        {day ? (
          <p>
            {LOAD[day.load] ?? day.load}: {range(day.low_g_per_kg, day.high_g_per_kg, "g/kg")}, which is {range(day.low_g, day.high_g, "g")} at {f.weight_kg} kg.
          </p>
        ) : (
          <p>
            Add your weight in <a className="underline" href="#/settings">Settings</a> to see a daily range.
          </p>
        )}
      </section>
      <section aria-label="Logged today" className="space-y-1">
        <h3 className="font-medium">Logged in SparkyFitness</h3>
        {!f.connected && !logged ? (
          <p>
            Connect SparkyFitness in <a className="underline" href="#/settings">Settings</a> to compare with what you have eaten.
          </p>
        ) : (
          <>
            {day && <p>{carbStatus(logged?.carbs_g, day.low_g, day.high_g)}</p>}
            {logged && (
              <dl className="space-y-0.5">
                <Row label="Energy" value={round(logged.kcal, "kcal")} />
                <Row label="Carbohydrate" value={round(logged.carbs_g, "g")} />
                <Row label="Protein" value={round(logged.protein_g, "g")} />
                <Row label="Fat" value={round(logged.fat_g, "g")} />
                <Row label="Water" value={round(logged.water_ml, "ml")} />
              </dl>
            )}
            <p className="text-muted-foreground">{logged?.synced_at ? `As of the last sync, ${logged.synced_at.replace("T", " ")}.` : "Nothing synced for today yet."}</p>
            {f.connected && (
              <Button size="sm" variant="outline" disabled={busy} onClick={sync}>
                {busy ? "Syncing…" : "Sync from SparkyFitness"}
              </Button>
            )}
            {msg && <p role="alert">{msg}</p>}
          </>
        )}
        {f.ride_kcal_approx != null && (
          <p>
            Today’s rides: about {f.ride_kcal_approx} kcal (approximate){logged?.kcal != null ? `, against ${Math.round(logged.kcal)} kcal logged` : ""}.
          </p>
        )}
      </section>
      <details className="text-xs text-muted-foreground">
        <summary>How these numbers are worked out</summary>
        <p>{f.hourly_method}</p>
        <p>{f.daily_method}</p>
        <p>{f.energy_method}</p>
      </details>
      <p className="text-xs text-muted-foreground">{f.note}</p>
    </div>
  )
}

/** #/fueling: today's carbohydrate guidance against what the rider has logged (#112). */
export function Fueling() {
  const [load, retry, refresh] = useLoad<FuelingData>(getFueling)
  return (
    <div className="mx-auto max-w-2xl" aria-label="Fueling">
      <Panel title="Fueling" load={load} retry={retry}>
        {(f) => <Body f={f} onSynced={refresh} />}
      </Panel>
    </div>
  )
}
