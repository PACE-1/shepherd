import { useState } from "react"

import type { WeatherLocation, WeatherPlace } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { clearLocation, getLocation, PRIVACY, placeLabel, saveLocation, searchPlaces } from "@/lib/weather"
import { Panel, useLoad } from "@/screens/panel"

/** Type a place name, search Open-Meteo's geocoder, pick a result. Says what is sent; degrades to a message. */
export function PlaceSearch({ onPick }: { onPick: (p: WeatherPlace) => void }) {
  const [q, setQ] = useState("")
  const [busy, setBusy] = useState(false)
  const [results, setResults] = useState<WeatherPlace[] | null>(null)
  const [message, setMessage] = useState("")

  const search = async (e: { preventDefault: () => void }) => {
    e.preventDefault()
    if (q.trim().length < 2) return setMessage("Type at least two letters of a town or city.")
    setBusy(true)
    setMessage("")
    setResults(null)
    try {
      const r = await searchPlaces(q.trim())
      if (!r.available) setMessage(r.message || "Place search is unavailable right now.")
      else if (!r.results.length) setMessage("No place found with that name. Try another spelling.")
      else setResults(r.results)
    } catch {
      setMessage("Place search is unavailable right now. You can continue without a location and add one later in Settings.")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-2 text-sm">
      <form className="flex flex-wrap items-end gap-2" onSubmit={search}>
        <Label className="flex-col items-start gap-1">
          Place name
          <Input className="w-56" value={q} placeholder="Town or city" onChange={(e) => setQ(e.target.value)} />
        </Label>
        <Button size="sm" type="submit" variant="outline" disabled={busy}>
          {busy ? "Searching…" : "Search"}
        </Button>
      </form>
      {message && <p role="status">{message}</p>}
      {results && (
        <ul className="space-y-1" aria-label="Places found">
          {results.map((p, i) => (
            <li key={i}>
              <Button size="sm" variant="ghost" className="h-auto whitespace-normal text-left" onClick={() => { setResults(null); setQ(""); onPick(p) }}>
                {placeLabel(p)}
              </Button>
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-muted-foreground">{PRIVACY}</p>
    </div>
  )
}

function LocationBody({ loc, reload }: { loc: WeatherLocation; reload: () => void }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [saved, setSaved] = useState("")
  const run = async (fn: () => Promise<unknown>, done: string) => {
    setBusy(true)
    setError("")
    setSaved("")
    try {
      await fn()
      setSaved(done)
      reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="space-y-3 text-sm">
      <p>
        {loc.place ? <>Riding near <b>{placeLabel(loc.place)}</b>.</> : "No location set, so no forecast is shown. That is fine: everything else works without it."}
      </p>
      <PlaceSearch onPick={(p) => run(() => saveLocation(p), `Saved ${placeLabel(p)}.`)} />
      {loc.place && (
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => run(clearLocation, "Location removed. The forecast is off.")}>
          Use no location
        </Button>
      )}
      {saved && <p role="status">{saved}</p>}
      {error && <p role="alert">Couldn’t save: {error}</p>}
    </div>
  )
}

/** Settings card, and the body of the guided-setup step. */
export function LocationCard({ title = "Weather location" }: { title?: string }) {
  const [load, retry, refresh] = useLoad<WeatherLocation>(getLocation)
  return (
    <Panel title={title} load={load} retry={retry}>
      {(loc) => <LocationBody loc={loc} reload={refresh} />}
    </Panel>
  )
}
