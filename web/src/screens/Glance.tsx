import type { IcuConnection, PlanRead, Readiness, RiderStats, SettingsRead, WeekSummary } from "@/api/types"
import { Card, CardContent } from "@/components/ui/card"
import {
  dayStatus,
  isDone,
  nextStep,
  sessionWords,
  todayPlan,
  weekProgress,
  type Level,
} from "@/lib/glance"
import { currentWeek, fmtMinutes, getReadiness, getWeekSummary, isoDay, reading } from "@/lib/home"
import { getSettings } from "@/lib/settings"
import { getIcuConnection } from "@/lib/setup"
import { CompanionToday } from "@/screens/CompanionToday"
import { useLoad, type Load } from "@/screens/panel"
import { SessionWeather } from "@/screens/WeatherSession"

const thisWeek = () => getWeekSummary(0)

// Colour is never the only signal: the headline says the same in words.
const TONE: Record<Level, string> = {
  ready: "border-emerald-500",
  easy: "border-amber-500",
  rest: "border-sky-500",
  unknown: "border-border",
}

const ok = <T,>(l: Load<T>) => (l.state === "ok" ? l.data : undefined)

/**
 * "At a glance" for riders who want one plain answer: how am I today, what do I ride, how is my week,
 * what should I set up next. Reads only existing endpoints; each source fails on its own.
 */
export function Glance({ plan, stats }: { plan: Load<PlanRead>; stats: Load<RiderStats> }) {
  const [readiness] = useLoad<Readiness>(getReadiness)
  const [week] = useLoad<WeekSummary>(thisWeek)
  const [conn] = useLoad<IcuConnection>(getIcuConnection)
  const [settings] = useLoad<SettingsRead>(getSettings)
  const today = isoDay()

  const p = ok(plan)
  const weeks = p?.plan_json?.weeks
  const pw = currentWeek(p?.plan_json, today)
  const tp = p ? todayPlan(weeks, pw, today) : ({ kind: "unknown" } as const)
  const load = ok(stats)?.load as Record<string, unknown> | null | undefined
  const tsb = reading(load?.tsb)
  const r = ok(readiness)
  const status = dayStatus({
    severity: r?.severity,
    score: r?.score_0_100,
    tsb,
    today: tp.kind === "sessions" ? "session" : tp.kind === "rest" ? "rest" : tp.kind === "none" ? "no-plan" : "unknown",
  })
  const progress = weekProgress(pw, ok(week)?.planned_days_done)
  const step = nextStep({
    connected: conn.state === "ok" ? conn.data.connected : null,
    riderSet: settings.state === "ok" ? settings.data.lthr_is_set : null,
    hasPlan: p ? !!weeks?.length : null,
  })

  return (
    <Card className="md:col-span-2" aria-label="At a glance">
      <CardContent className="space-y-4 p-4">
        <h2 className="text-sm font-semibold">At a glance</h2>
        <div className={`border-l-4 pl-3 ${TONE[status.level]}`}>
          <p className="text-lg font-semibold">{status.headline}</p>
          <p className="text-sm text-muted-foreground">{status.why}</p>
          {tsb !== null && (
            <p className="mt-1 text-xs text-muted-foreground">
              Form score {Math.round(tsb)}: your fitness minus your tiredness. Below zero means you are carrying some fatigue, which is normal while training.
            </p>
          )}
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <section aria-label="Your session">
            <h3 className="text-xs font-semibold text-muted-foreground">Your session</h3>
            {plan.state === "loading" && <p className="text-sm text-muted-foreground">Loading…</p>}
            {plan.state === "error" && <p className="text-sm">Couldn’t read your plan.</p>}
            {tp.kind === "none" && <p className="text-sm">No training plan covers today. <a className="underline" href="#/plan">Open Training Plan</a> to set one up.</p>}
            {tp.kind === "rest" && <p className="text-sm">No ride planned. Enjoy the rest.</p>}
            {tp.kind === "sessions" && (
              <ul className="space-y-1">
                {tp.sessions.map((s, i) => (
                  <li key={i} className="text-sm">
                    <span className="font-medium">{s.zwo_name || s.session_type}</span> · {fmtMinutes(s.duration_min)}
                    {isDone(s) ? " · done" : ""}
                    <span className="block text-xs text-muted-foreground">{sessionWords(s.session_type)}</span>
                    {!isDone(s) && <SessionWeather day={today} swapHref="#/plan" />}
                  </li>
                ))}
              </ul>
            )}
            <CompanionToday />
          </section>

          <section aria-label="Your week">
            <h3 className="text-xs font-semibold text-muted-foreground">Your week</h3>
            {progress ? (
              <>
                <p className="text-sm">
                  <b>{progress.done}</b> of {progress.planned} planned {progress.planned === 1 ? "ride" : "rides"} done
                </p>
                <progress className="h-2 w-full" max={Math.max(progress.planned, 1)} value={progress.done} aria-label="Rides done this week" />
              </>
            ) : (
              <p className="text-sm text-muted-foreground">{plan.state === "ok" ? "No plan week covers today." : "—"}</p>
            )}
          </section>
        </div>

        {step && (
          <p className="rounded-lg bg-muted p-3 text-sm">
            <span className="font-medium">Next step: </span>
            <a className="underline" href={step.href}>{step.label}</a>. {step.why}
          </p>
        )}
      </CardContent>
    </Card>
  )
}
