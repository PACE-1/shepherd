import { useEffect, useState } from "react"

import type { WorkoutRow } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/native-select"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { getTags, listWorkouts, PAGE, SORTS, suitsGravel, TYPES, type Outdoor, type WorkoutQuery } from "@/lib/library"
import { WorkoutCard } from "@/screens/WorkoutCard"
import { RunWorkouts } from "@/screens/RunWorkouts"

type Load = { state: "loading" } | { state: "ok"; rows: WorkoutRow[]; total: number | null } | { state: "error"; message: string }

const num = (v: string) => (v === "" ? null : Number(v))

export function Library() {
  const EMPTY: WorkoutQuery = { search: "", minDuration: null, maxDuration: null, sort: "score_desc", contentClass: "", tags: [] }
  const [q, setQ] = useState<WorkoutQuery>(EMPTY)
  const [gravel, setGravel] = useState(false)
  const [tags, setTags] = useState<string[]>([])
  const [outdoor, setOutdoor] = useState<Outdoor>({ on: false, transitMin: 10, spinMin: 20 })
  const [applied, setApplied] = useState(q)
  const [load, setLoad] = useState<Load>({ state: "loading" })
  const [attempt, setAttempt] = useState(0)

  // Typing waits for a short pause before it asks the server.
  useEffect(() => {
    const t = setTimeout(() => setApplied(q), 300)
    return () => clearTimeout(t)
  }, [q])

  useEffect(() => {
    let live = true
    // eslint-disable-next-line react-hooks/set-state-in-effect -- the loading flash on a new query or retry is intended
    setLoad({ state: "loading" })
    listWorkouts(applied).then(
      (r) => live && setLoad({ state: "ok", ...r }),
      (e: unknown) => live && setLoad({ state: "error", message: e instanceof Error ? e.message : String(e) }),
    )
    return () => { live = false }
  }, [applied, attempt])

  // Tags are optional polish: if they fail to load, the rest of the library works.
  useEffect(() => {
    getTags().then(setTags, () => {})
  }, [])

  const badRange = q.minDuration !== null && q.maxDuration !== null && q.minDuration > q.maxDuration

  const rows = load.state === "ok" ? (gravel ? load.rows.filter((w) => suitsGravel(w)) : load.rows) : []

  return (
    <div className="space-y-4">
      <RunWorkouts />
      <Card>
        <CardContent className="space-y-3 p-4">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-sm font-semibold">Workout library</h2>
            <Button size="sm" className="max-md:min-h-11" render={<a href="#/builder" />}>New workout</Button>
          </div>
          <div className="flex flex-wrap items-end gap-2 text-sm">
            <Label className="flex-col items-start gap-1">
              Search
              <Input type="search"  placeholder="3x16, vo2, sweet spot…" value={q.search} onChange={(e) => setQ({ ...q, search: e.target.value })} />
            </Label>
            <Label className="flex-col items-start gap-1">
              From (min)
              <Input type="number" min={0} className="w-24" value={q.minDuration ?? ""} onChange={(e) => setQ({ ...q, minDuration: num(e.target.value) })} />
            </Label>
            <Label className="flex-col items-start gap-1">
              To (min)
              <Input type="number" min={0} className="w-24" value={q.maxDuration ?? ""} onChange={(e) => setQ({ ...q, maxDuration: num(e.target.value) })} />
            </Label>
            <Label className="flex-col items-start gap-1">
              Sort
              <NativeSelect  value={q.sort} onChange={(e) => setQ({ ...q, sort: e.target.value })}>
                {SORTS.map(([id, label]) => (
                  <option key={id} value={id}>
                    {label}
                  </option>
                ))}
              </NativeSelect>
            </Label>
          </div>
          <div className="flex flex-wrap items-end gap-2 text-sm">
            <Label className="flex-col items-start gap-1">
              Type
              <NativeSelect value={q.contentClass} onChange={(e) => setQ({ ...q, contentClass: e.target.value })}>
                <option value="">All types</option>
                {TYPES.map(([group, items]) => (
                  <optgroup key={group} label={group}>
                    {items.map(([id, label]) => (
                      <option key={id} value={id}>
                        {label}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </NativeSelect>
            </Label>
            <Label className="gap-2">
              <Checkbox checked={gravel} onCheckedChange={(v) => setGravel(v === true)} />
              Suits gravel and cobbles
            </Label>
            <Button size="sm" variant="ghost" onClick={() => { setQ(EMPTY); setGravel(false) }}>
              Clear filters
            </Button>
          </div>
          {tags.length > 0 && (
            <div role="group" aria-label="Tags" className="flex flex-wrap gap-1">
              {tags.map((t) => (
                <Button
                  key={t}
                  size="xs"
                  variant={q.tags.includes(t) ? "default" : "outline"}
                  aria-pressed={q.tags.includes(t)}
                  onClick={() => setQ({ ...q, tags: q.tags.includes(t) ? q.tags.filter((x) => x !== t) : [...q.tags, t] })}
                >
                  {t}
                </Button>
              ))}
            </div>
          )}
          <div className="flex flex-wrap items-end gap-2 text-sm">
            <Label className="gap-2">
              <Checkbox checked={outdoor.on} onCheckedChange={(v) => setOutdoor({ ...outdoor, on: v === true })} />
              Outdoor variant for downloads
            </Label>
            {outdoor.on && (
              <>
                <Label className="flex-col items-start gap-1">
                  Ride to the climb (min)
                  <Input type="number" min={0} max={120} className="w-24" value={outdoor.transitMin} onChange={(e) => setOutdoor({ ...outdoor, transitMin: Math.min(120, Math.max(0, Number(e.target.value) || 0)) })} />
                </Label>
                <Label className="flex-col items-start gap-1">
                  Spin home (min)
                  <Input type="number" min={0} max={180} className="w-24" value={outdoor.spinMin} onChange={(e) => setOutdoor({ ...outdoor, spinMin: Math.min(180, Math.max(0, Number(e.target.value) || 0)) })} />
                </Label>
                <p className="w-full text-muted-foreground">These minutes are added easy riding, not counted in your planned weekly load.</p>
              </>
            )}
          </div>
          {badRange && <p className="text-sm">“From” is longer than “To”.</p>}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="space-y-2 p-4">
          {load.state === "loading" && <p className="text-sm text-muted-foreground">Loading…</p>}
          {load.state === "error" && (
            <div role="alert" className="text-sm">
              <p>Couldn’t load the library: {load.message}</p>
              <Button className="mt-2" size="sm" variant="outline" onClick={() => setAttempt(attempt + 1)}>
                Retry
              </Button>
            </div>
          )}
          {load.state === "ok" &&
            (rows.length === 0 ? (
              <p className="text-sm">No workouts match.</p>
            ) : (
              <>
                <p className="text-sm text-muted-foreground" aria-live="polite">
                  Showing {rows.length}
                  {load.total !== null ? ` of ${load.total}` : ""}
                  {load.rows.length >= PAGE ? ". Narrow the search to see others." : ""}
                </p>
                <ul className="divide-y">
                  {rows.map((w) => (
                    <WorkoutCard key={`${w.Category}/${w.File}`} w={w} outdoor={outdoor} />
                  ))}
                </ul>
              </>
            ))}
        </CardContent>
      </Card>
    </div>
  )
}
