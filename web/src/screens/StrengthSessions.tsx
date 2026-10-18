import { useCallback, useState } from "react"

import type { StrengthSession, StrengthSessions as Data } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/native-select"
import { fmtMinutes } from "@/lib/home"
import { getStrengthSessions, loadText, prescription, range } from "@/lib/strength"
import { Panel, useLoad } from "@/screens/panel"

// Printing shows only the chosen session: the navigation and the other cards are hidden.
const PRINT_CSS = "@media print { nav[aria-label='Sections'] { display: none !important } }"

function Session({ s, data }: { s: StrengthSession; data: Data }) {
  return (
    <article aria-label={s.name} className="space-y-3">
      <header className="space-y-1">
        <h2 className="text-base font-semibold">{s.name}</h2>
        <p className="text-sm">{s.intent}</p>
        <p className="text-sm text-muted-foreground">
          {fmtMinutes(s.minutes)}
          {s.warmup_min ? `, including a ${s.warmup_min} minute warm-up (easy, joints warm)` : ""}
          {" · "}effort about {range(s.rpe_range)} out of 10
        </p>
        <p className="text-sm">
          Load {loadText(s.load_au, s.load_note)}.
        </p>
      </header>
      <ol className="divide-y">
        {s.exercises.map((e, i) => (
          <li key={e.id} className="space-y-0.5 py-2 text-sm">
            <p>
              <span className="font-medium">
                {i + 1}. {e.name}
              </span>
              {": "}
              {prescription(e)}
            </p>
            <p className="text-muted-foreground">
              Effort: {e.effort} Rest: {e.rest}.
            </p>
            <p className="text-muted-foreground">Cue: {e.cue}</p>
          </li>
        ))}
      </ol>
      {s.progression && (
        <p className="text-xs text-muted-foreground">
          This stage: {range(s.progression.sets)} sets of {range(s.progression.reps)} repetitions, {s.progression.rest}; {s.progression.pct_1rm}.
          {s.progression.verify ? " These ranges are not checked against the paper yet (verify)." : ""}
        </p>
      )}
      <p className="text-xs text-muted-foreground">{s.load_method}</p>
      <p className="text-xs text-muted-foreground">Source: {s.source}.</p>
      <p role="note" className="text-sm font-medium">
        {data.disclaimer}
      </p>
      <p className="text-xs text-muted-foreground">{data.not_validated}</p>
    </article>
  )
}

/** Browse the strength and mobility sessions the plan can place next to your rides; print one. */
export function StrengthSessions() {
  const [stage, setStage] = useState("novice")
  const fetcher = useCallback(() => getStrengthSessions(stage), [stage])
  const [load, retry] = useLoad(fetcher)
  const [pick, setPick] = useState("")
  return (
    <div className="space-y-4">
      <style>{PRINT_CSS}</style>
      <h1 className="text-lg font-semibold">Strength and mobility</h1>
      <p role="note" className="text-sm print:hidden">
        General fitness guidance, not individual medical or coaching advice. Stop if anything hurts.
      </p>
      <Panel title="Sessions" load={load} retry={retry}>
        {(d) => {
          const chosen = d.sessions.find((s) => s.id === pick) ?? d.sessions[0]
          const st = d.stages.find((x) => x.id === d.stage)
          return (
            <div className="space-y-4">
              <div className="space-y-1 print:hidden">
                <Label htmlFor="strength-stage">Training stage</Label>
                <NativeSelect id="strength-stage" value={stage} onChange={(e) => setStage(e.target.value)}>
                  {d.stages.map((x) => (
                    <option key={x.id} value={x.id}>
                      {x.label}
                    </option>
                  ))}
                </NativeSelect>
                {st && (
                  <p className="text-xs text-muted-foreground">
                    {st.effort} {st.verify ? "(Ranges for this stage are not checked against the paper yet: verify.)" : ""}
                  </p>
                )}
              </div>
              <div role="group" aria-label="Sessions" className="flex flex-wrap gap-2 print:hidden">
                {d.sessions.map((s) => (
                  <Button key={s.id} size="sm" variant={s.id === chosen.id ? "default" : "outline"} aria-pressed={s.id === chosen.id} onClick={() => setPick(s.id)}>
                    {s.name}
                  </Button>
                ))}
              </div>
              <Session s={chosen} data={d} />
              <div className="print:hidden">
                <Button size="sm" variant="outline" onClick={() => window.print()}>
                  Print this session
                </Button>
              </div>
              <p className="text-xs text-muted-foreground print:hidden">Sources: {d.sources.join("; ")}.</p>
            </div>
          )
        }}
      </Panel>
    </div>
  )
}
