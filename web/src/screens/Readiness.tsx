import { useState } from "react"

import type { AutoAdjustResult, Readiness as ReadinessRead, SportsLoad, TodaySession } from "@/api/types"
import { Button } from "@/components/ui/button"
import { acceptAdjusted, autoAdjust, easeToday, fmtMinutes, getReadiness, getTodaySession, rideOriginal } from "@/lib/home"
import { readinessDrivers, recentLoadByType } from "@/lib/readinessDrivers"
import { getSportsLoad } from "@/lib/sports"
import { Panel, useLoad } from "@/screens/panel"
import { RetestNudge, type Nudge } from "@/screens/RetestNudge"

const WORD: Record<string, string> = { normal: "Ready to train", tier_down: "Ease off today", rest: "Rest advised" }

type Preview = { scope: "week" | "day"; severity: string; result: AutoAdjustResult }

const actionLine = (a: Record<string, unknown>) => {
  const after = (a.after as { type?: string } | undefined)?.type
  return `${String(a.day ?? "")}${after ? ` → ${after}` : ""}`
}

function Actions({ r, t, reload }: { r: ReadinessRead; t: TodaySession | null; reload: () => void }) {
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState("")
  const [error, setError] = useState("")
  const [preview, setPreview] = useState<Preview | null>(null)

  const run = async (work: () => Promise<string>) => {
    setBusy(true)
    setError("")
    setMessage("")
    try {
      setMessage(await work())
      reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const adjusted = t?.was_modified ? t.adjusted : null
  const showPreview = async () => {
    const scope = r.severity === "rest" ? "day" : "week"
    setBusy(true)
    setError("")
    try {
      setPreview({ scope, severity: r.severity, result: await autoAdjust(scope, true, r.severity) })
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-2">
      {adjusted && t?.planned && (
        <div className="space-y-2 text-sm">
          <p>
            Suggested today: <span className="font-medium">{adjusted.session_type}</span> · {fmtMinutes(adjusted.duration_min)} instead of{" "}
            {t.planned.session_type}. {t.adjustment_reason || t.reason}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              disabled={busy}
              onClick={() => run(async () => { await acceptAdjusted(adjusted, t.adjustment_reason || t.reason || "adapted"); return "Today’s session changed." })}
            >
              Use the suggestion
            </Button>
            <Button size="sm" variant="outline" disabled={busy} onClick={() => run(async () => { await rideOriginal(); return "Original session kept for today." })}>
              Ride the original
            </Button>
          </div>
        </div>
      )}
      {r.severity === "tier_down" && (
        <Button
          size="sm"
          disabled={busy}
          onClick={() =>
            run(async () => {
              const res = await easeToday()
              return res.ok ? `Eased: ${res.old_type} → ${res.new_type}.` : `Nothing changed (${(res.action ?? "no change").replace(/_/g, " ")}).`
            })
          }
        >
          Ease today’s session
        </Button>
      )}
      {r.severity !== "normal" && !preview && (
        <Button size="sm" variant="outline" disabled={busy} onClick={showPreview}>
          {r.severity === "rest" ? "Apply rest day…" : "Adjust this week…"}
        </Button>
      )}
      {preview && (
        <div className="space-y-2 text-sm">
          {preview.result.note && <p>{preview.result.note}</p>}
          {preview.result.actions.length === 0 ? (
            <p>No sessions would change.</p>
          ) : (
            <ul className="list-disc pl-5">
              {preview.result.actions.map((a, i) => (
                <li key={i}>{actionLine(a)}</li>
              ))}
            </ul>
          )}
          <div className="flex gap-2">
            <Button
              size="sm"
              disabled={busy || preview.result.actions.length === 0}
              onClick={() =>
                run(async () => {
                  const res = await autoAdjust(preview.scope, false, preview.severity)
                  setPreview(null)
                  return `${res.sessions_modified} session(s) changed.`
                })
              }
            >
              Confirm
            </Button>
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => setPreview(null)}>
              Cancel
            </Button>
          </div>
        </div>
      )}
      {message && <p className="text-sm" role="status">{message}</p>}
      {error && <p role="alert" className="text-sm">Couldn’t do that: {error}</p>}
    </div>
  )
}

/** What is driving fatigue: the last 7 days of training load, split by sport. */
function RecentLoad({ data }: { data: SportsLoad }) {
  const { rows, total } = recentLoadByType(data)
  return (
    <div className="space-y-1 text-sm">
      <p className="font-medium">Training load, last 7 days</p>
      {rows.length === 0 ? (
        <p className="text-muted-foreground">No training load recorded in the last 7 days.</p>
      ) : (
        <ul>
          {rows.map((x) => (
            <li key={x.sport}>{x.name}: {x.load}</li>
          ))}
          <li className="text-muted-foreground">All sports: {total}</li>
        </ul>
      )}
    </div>
  )
}

export function Readiness() {
  const [readiness, retryReadiness] = useLoad<ReadinessRead>(getReadiness)
  const [today, retryToday] = useLoad<TodaySession>(getTodaySession)
  const [sports] = useLoad<SportsLoad>(getSportsLoad)
  const reload = () => { retryReadiness(); retryToday() }

  return (
    <Panel title="Readiness" load={readiness} retry={retryReadiness}>
      {(r) => {
        const reason = r.severity_reasons[0] || r.readiness?.advice || ""
        const drivers = readinessDrivers(r)
        return (
          <div className="space-y-2">
            <p className="text-sm">
              <span className="font-medium">{WORD[r.severity] ?? "Train as planned"}</span>
              {r.score_0_100 != null && <span className="text-muted-foreground"> · {Math.round(r.score_0_100)}/100</span>}
            </p>
            {reason && <p className="text-sm text-muted-foreground">{reason}</p>}
            {drivers && <p className="text-sm text-muted-foreground">{drivers}</p>}
            {sports.state === "ok" && <RecentLoad data={sports.data} />}
            <Actions r={r} t={today.state === "ok" ? today.data : null} reload={reload} />
            {today.state === "ok" && today.data.retest_nudge && <RetestNudge n={today.data.retest_nudge as Nudge} />}
          </div>
        )
      }}
    </Panel>
  )
}
