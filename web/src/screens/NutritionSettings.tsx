import { useState } from "react"

import type { NutritionConnection } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { deleteNutrition, getNutrition, saveNutrition, syncNutrition, testNutrition } from "@/lib/nutrition"
import { Panel, useLoad } from "@/screens/panel"

const message = (e: unknown) => (e instanceof Error ? e.message : String(e))

const PRIVACY =
  "Shepherd reads only daily totals (calories, carbohydrate, protein, fat and water) from your own SparkyFitness server. The key is stored on this computer and sent only to the address above."

function Connect({ c, onChange }: { c: NutritionConnection; onChange: () => void }) {
  const [url, setUrl] = useState(c.base_url)
  const [key, setKey] = useState("")
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState("")
  const [error, setError] = useState("")
  const run = async (what: () => Promise<string>) => {
    setBusy(true)
    setMsg("")
    setError("")
    try {
      setMsg(await what())
    } catch (e) {
      setError(message(e))
    } finally {
      setBusy(false)
    }
  }
  const save = () =>
    run(async () => {
      await saveNutrition(url, key)
      setKey("")
      onChange()
      return "Saved."
    })
  const test = () => run(async () => (await testNutrition()).message)
  const sync = () =>
    run(async () => {
      const r = await syncNutrition()
      onChange()
      return `Synced ${r.start} to ${r.end}: ${r.days_with_data} ${r.days_with_data === 1 ? "day" : "days"} with entries.`
    })
  const disconnect = () =>
    run(async () => {
      await deleteNutrition()
      setUrl("")
      setKey("")
      onChange()
      return "Disconnected. Days already synced are kept."
    })
  return (
    <div className="space-y-3 text-sm">
      <p>
        {c.configured ? `Connected to ${c.base_url}.` : "SparkyFitness is not connected."}
        {c.last_synced_at ? ` Last sync: ${c.last_synced_at.replace("T", " ")}.` : ""}
      </p>
      <div className="grid gap-3">
        <Label className="flex-col items-start gap-1">
          SparkyFitness address
          <Input className="w-full" value={url} placeholder="http://192.168.1.20:3004" onChange={(e) => setUrl(e.target.value)} />
        </Label>
        <Label className="flex-col items-start gap-1">
          SparkyFitness API key
          <Input
            className="w-full"
            type="password"
            autoComplete="off"
            value={key}
            placeholder={c.has_key ? "Saved. Leave empty to keep it for the same address." : "Create a read-only key in SparkyFitness, Settings, API keys"}
            onChange={(e) => setKey(e.target.value)}
          />
        </Label>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" disabled={busy || !url.trim()} onClick={save}>
          Save
        </Button>
        <Button size="sm" variant="outline" disabled={busy || !c.configured} onClick={test}>
          Test connection
        </Button>
        <Button size="sm" variant="outline" disabled={busy || !c.configured} onClick={sync}>
          Sync nutrition now
        </Button>
        {c.configured && (
          <Button size="sm" variant="ghost" disabled={busy} onClick={disconnect}>
            Disconnect
          </Button>
        )}
      </div>
      {msg && <p role="status">{msg}</p>}
      {error && <p role="alert">Couldn’t do that: {error}</p>}
      <p className="text-xs text-muted-foreground">
        {PRIVACY} Syncs only when you press Sync nutrition now. <a className="underline" href="#/fueling">Open Fueling</a>
      </p>
    </div>
  )
}

/** Settings card: connect a self-hosted SparkyFitness server for daily nutrition totals (#112). */
export function NutritionSettings() {
  const [load, retry, refresh] = useLoad<NutritionConnection>(getNutrition)
  return (
    <Panel title="Nutrition (SparkyFitness)" load={load} retry={retry}>
      {(c) => <Connect c={c} onChange={refresh} />}
    </Panel>
  )
}
