import { useCallback, useEffect, useState } from "react"

import type { PlanRead, PlanWeek } from "@/api/types"
import { Button, buttonVariants } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { NativeSelect } from "@/components/ui/native-select"
import { Input } from "@/components/ui/input"
import { PlanGenerate } from "@/screens/PlanGenerate"
import { autoRecalc, getDailyAdapt, summaryImageUrl, updatePlan } from "@/lib/plan"
import { GoalEvent } from "@/screens/GoalEvent"
import { PlanAvailability } from "@/screens/PlanAvailability"
import { PlanCalendar } from "@/screens/PlanCalendar"
import { PlanRace } from "@/screens/PlanRace"
import { PlanRedraw } from "@/screens/PlanRedraw"
import { PlanRematch } from "@/screens/PlanRematch"
import { PlanTimeOff } from "@/screens/PlanTimeOff"
import { SessionExport } from "@/screens/SessionExport"
import { SessionWeather } from "@/screens/WeatherSession"
import { WeekCompanions } from "@/screens/WeekCompanions"
import { currentWeek, dismissSession, FTP_TEST_TYPES, fmtMinutes, getPlan, isoDay, moveSession, plannedTss, revertDeload, setFtpTestType, SWAP_TYPES, swapSessionType, weekSessions, type Availability } from "@/lib/home"

type Load = { state: "loading" } | { state: "ok"; plan: PlanRead } | { state: "error"; message: string }

const STATUS_LABEL: Record<string, string> = {
  done: "done",
  done_partial: "done (partly)",
  missed: "missed",
  dismissed: "dismissed",
  ambiguous: "needs review",
}
const statusLabel = (status: string) =>
  status.startsWith("moved_from:") ? "moved" : (STATUS_LABEL[status] ?? "")

const dayLabel = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })

export function Plan() {
  const [load, setLoad] = useState<Load>({ state: "loading" })
  const [index, setIndex] = useState<number | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [actionError, setActionError] = useState("")
  const [moving, setMoving] = useState<{ day: string; to: string } | null>(null)
  const [tool, setTool] = useState<"timeoff" | "race" | "availability" | "rematch" | "replace" | null>(null)
  const [redrawing, setRedrawing] = useState<string | null>(null)
  const [view, setView] = useState<"weeks" | "calendar">("weeks")
  const [updating, setUpdating] = useState(false)
  const [updateMsg, setUpdateMsg] = useState("")
  const [updateError, setUpdateError] = useState("")
  const [adapt, setAdapt] = useState("")
  const [swapping, setSwapping] = useState<{ day: string; type: string; minutes: number } | null>(null)
  const today = isoDay()

  const load0 = useCallback(() => {
    getPlan().then(
      (plan) => setLoad({ state: "ok", plan }),
      (e: unknown) => setLoad({ state: "error", message: e instanceof Error ? e.message : String(e) }),
    )
  }, [])
  const run = useCallback(() => {
    setLoad({ state: "loading" })
    load0()
  }, [load0])
  useEffect(load0, [load0])

  // Re-read in place, without the loading flash (a drag on the calendar, an update).
  const reread = useCallback(async () => {
    try {
      setLoad({ state: "ok", plan: await getPlan() })
    } catch {
      /* the next full load will say what is wrong */
    }
  }, [])
  // The daily-adapt call only ever projects; a hint is shown if it has one.
  useEffect(() => {
    getDailyAdapt().then(
      (d) => {
        const first = (d.projected_adaptations?.[0] ?? null) as { reason?: string; note?: string } | null
        setAdapt(first ? `Suggested adjustment: ${first.reason ?? first.note ?? "a change to this week"}. Use Update plan to apply it.` : "")
      },
      () => {},
    )
  }, [])
  // A plan older than a week rebuilds itself when the page opens. A failure here is not worth a message.
  useEffect(() => {
    autoRecalc().then(
      (r) => {
        if (r.action !== "recalculated") return
        setUpdateMsg(`Plan refreshed (${r.weeks_regenerated ?? 0} weeks updated).`)
        reread()
      },
      () => {},
    )
  }, [reread])
  const updateNow = async () => {
    setUpdating(true)
    setUpdateError("")
    setUpdateMsg("")
    try {
      const r = await updatePlan()
      setUpdateMsg(r.status_message || (r.action === "skipped" ? "Nothing needed changing." : "Plan updated."))
      await reread()
    } catch (e) {
      setUpdateError(e instanceof Error ? e.message : String(e))
    } finally {
      setUpdating(false)
    }
  }

  // Dismiss or restore the day's session, then re-read the plan in place (no loading flash).
  const change = async (day: string, action: () => Promise<unknown>) => {
    setBusy(day)
    setActionError("")
    try {
      await action()
      const plan = await getPlan()
      setLoad({ state: "ok", plan })
      return true
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
      return false
    } finally {
      setBusy(null)
    }
  }
  const toggleDismissed = (day: string, undo: boolean) => change(day, () => dismissSession(day, undo))
  const confirmSwap = async () => {
    if (swapping && (await change(swapping.day, () => swapSessionType(swapping.day, swapping.type, swapping.minutes)))) setSwapping(null)
  }
  const confirmMove = async () => {
    if (moving && (await change(moving.day, () => moveSession(moving.day, moving.to)))) setMoving(null)
  }

  if (load.state === "loading") return <p className="text-sm text-muted-foreground">Loading…</p>
  if (load.state === "error")
    return (
      <div role="alert" className="text-sm">
        <p>Couldn’t load the plan: {load.message}</p>
        <Button className="mt-2" size="sm" variant="outline" onClick={run}>
          Retry
        </Button>
      </div>
    )

  const plan = load.plan.plan_json
  const weeks: PlanWeek[] = plan?.weeks ?? []
  if (!weeks.length)
    return (
      <div className="space-y-4">
        <p className="text-sm font-medium">No training plan yet.</p>
        <PlanGenerate hasPlan={false} onDone={run} />
      </div>
    )

  const startAt = weeks.indexOf(currentWeek(plan, today) ?? weeks[0])
  const i = Math.min(Math.max(index ?? startAt, 0), weeks.length - 1)
  const week = weeks[i]
  const sessions = weekSessions(week)
  const goal = plan.goal
  const openWeek = (start: string) => {
    const k = weeks.findIndex((w) => w.start === start)
    if (k >= 0) setIndex(k)
    setView("weeks")
  }
  const drift = plan.ctl_drift as { exceeded?: boolean; snapshot_ctl: number; live_ctl: number } | null | undefined
  const deload = (plan as { deload_advance?: { reverted?: boolean; week_num?: number } }).deload_advance
  const canUndoDeload = !!deload && !deload.reverted
  const undoDeload = async () => {
    setBusy("deload")
    setActionError("")
    try {
      const r = await revertDeload()
      if (!r.reverted) setActionError(`Nothing was undone (${(r.reason ?? "no change").replace(/_/g, " ")}).`)
      setLoad({ state: "ok", plan: await getPlan() })
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-4">
      <GoalEvent />

      <Card>
        <CardContent className="space-y-1 p-4">
          <h2 className="text-sm font-semibold">Plan</h2>
          <p className="text-sm text-muted-foreground">
            {goal?.event_name || goal?.type || "Training plan"}
            {goal?.hours_per_week ? ` · ${goal.hours_per_week} h/week` : ""} · {weeks.length} weeks
            {goal?.event_date ? ` · event ${goal.event_date}` : ""}
          </p>
          {!!plan.phases?.length && (
            <p className="text-sm text-muted-foreground">
              {plan.phases.map((p) => `${p.name} (${p.weeks} wk)`).join(" → ")}
            </p>
          )}
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant={view === "weeks" ? "default" : "outline"} aria-pressed={view === "weeks"} onClick={() => setView("weeks")}>
          Weeks
        </Button>
        <Button size="sm" variant={view === "calendar" ? "default" : "outline"} aria-pressed={view === "calendar"} onClick={() => setView("calendar")}>
          Calendar
        </Button>
        <Button size="sm" variant="outline" disabled={updating} onClick={updateNow}>
          {updating ? "Updating…" : "Update plan"}
        </Button>
        <a className={buttonVariants({ size: "sm", variant: "ghost" })} href={summaryImageUrl} target="_blank" rel="noopener noreferrer">
          Summary image
        </a>
      </div>
      {drift?.exceeded && (
        <p role="note" className="text-sm">
          The plan assumes fitness {Math.round(drift.snapshot_ctl)}; you are at {Math.round(drift.live_ctl)}.{" "}
          <button type="button" className="underline underline-offset-2" onClick={() => setTool("replace")}>
            Re-plan
          </button>
          ?
        </p>
      )}
      {updateMsg && <p role="status" className="text-sm">{updateMsg}</p>}
      {updateError && <p role="alert" className="text-sm">Couldn’t update the plan: {updateError}</p>}
      {adapt && <p role="note" className="text-sm text-muted-foreground">{adapt}</p>}

      {view === "calendar" ? (
        <PlanCalendar onOpenWeek={openWeek} onChanged={reread} />
      ) : (
        <Card>
          <CardContent className="space-y-3 p-4">
            <div className="flex items-center justify-between gap-2">
              <Button size="sm" variant="outline" disabled={i === 0} onClick={() => setIndex(i - 1)}>
                Previous week
              </Button>
              <h2 className="text-sm font-semibold" aria-live="polite">
                Week {week.week_num} · {week.phase}
                {week.is_stepback ? " · recovery" : ""}
              </h2>
              <Button size="sm" variant="outline" disabled={i === weeks.length - 1} onClick={() => setIndex(i + 1)}>
                Next week
              </Button>
            </div>
            <p className="text-sm text-muted-foreground">
              {dayLabel(week.start)} to {dayLabel(week.end)} · {plannedTss(sessions)} of {Math.round(week.tss_target)} TSS planned
            </p>
            {sessions.length === 0 ? (
              <p className="text-sm">No sessions this week.</p>
            ) : (
              <ul className="divide-y">
                {sessions.map((s, k) => {
                  const extra = statusLabel(s.status)
                  const dismissed = s.status === "dismissed"
                  const canToggle = !s.is_race && !s.status.startsWith("done")
                  return (
                    <li key={k} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                      <span className={`min-w-56 flex-1 ${s.day === today ? "font-medium" : ""}`} aria-current={s.day === today ? "date" : undefined}>
                        {dayLabel(s.day)} · {s.zwo_name || s.session_type}
                      </span>
                      <span className="text-muted-foreground">
                        {fmtMinutes(s.duration_min)} · {Math.round(s.tss_estimate)} TSS{extra ? ` · ${extra}` : ""}
                      </span>
                      {canToggle && !dismissed && moving?.day !== s.day && (
                        <Button
                          size="sm"
                          variant="ghost"
                          aria-label={`Move ${dayLabel(s.day)}`}
                          onClick={() => setMoving({ day: s.day, to: "" })}
                        >
                          Move
                        </Button>
                      )}
                      {canToggle && !dismissed && swapping?.day !== s.day && (
                        <Button
                          size="sm"
                          variant="ghost"
                          aria-label={`Change type ${dayLabel(s.day)}`}
                          onClick={() => setSwapping({ day: s.day, type: s.session_type, minutes: s.duration_min })}
                        >
                          Change type
                        </Button>
                      )}
                      {canToggle && !dismissed && redrawing !== s.day && (
                        <Button size="sm" variant="ghost" aria-label={`Other workout ${dayLabel(s.day)}`} onClick={() => setRedrawing(s.day)}>
                          Other workout
                        </Button>
                      )}
                      {redrawing === s.day && (
                        <PlanRedraw day={s.day} onDone={async () => { setRedrawing(null); setLoad({ state: "ok", plan: await getPlan() }) }} onCancel={() => setRedrawing(null)} />
                      )}
                      {canToggle && !dismissed && s.session_type === "ftp_test" && (
                        <NativeSelect
                          aria-label={`Test type ${dayLabel(s.day)}`}
                          className="text-sm"
                          value={String((s as { ftp_test_type?: string }).ftp_test_type ?? "")}
                          disabled={busy === s.day}
                          onChange={(e) => change(s.day, () => setFtpTestType(s.day, e.target.value))}
                        >
                          <option value="" disabled>
                            Test type…
                          </option>
                          {FTP_TEST_TYPES.map(([id, label]) => (
                            <option key={id} value={id}>
                              {label}
                            </option>
                          ))}
                        </NativeSelect>
                      )}
                      {swapping?.day === s.day && (
                        <span className="flex flex-wrap items-center gap-2">
                          <NativeSelect
                            aria-label="New type"
                            className="text-sm"
                            value={swapping.type}
                            onChange={(e) => setSwapping({ ...swapping, type: e.target.value })}
                          >
                            {SWAP_TYPES.map(([id, label]) => (
                              <option key={id} value={id}>
                                {label}
                              </option>
                            ))}
                          </NativeSelect>
                          <Input
                            type="number"
                            aria-label="Minutes"
                            className="w-20 text-sm"
                            min={30}
                            max={300}
                            value={swapping.minutes}
                            onChange={(e) => setSwapping({ ...swapping, minutes: Number(e.target.value) })}
                          />
                          <Button size="sm" disabled={busy === s.day || swapping.minutes < 30} onClick={confirmSwap}>
                            Apply
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => setSwapping(null)}>
                            Cancel
                          </Button>
                        </span>
                      )}
                      {moving?.day === s.day && (
                        <span className="flex items-center gap-2">
                          <Input
                            type="date"
                            aria-label="Move to"
                            className="text-sm"
                            min={today}
                            value={moving.to}
                            onChange={(e) => setMoving({ day: s.day, to: e.target.value })}
                          />
                          <Button size="sm" disabled={!moving.to || busy === s.day} onClick={confirmMove}>
                            Move here
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => setMoving(null)}>
                            Cancel
                          </Button>
                        </span>
                      )}
                      {s.zwo_file && !dismissed && (
                        <SessionExport file={s.zwo_file} day={s.day} name={s.zwo_name || s.session_type} type={s.session_type} minutes={s.duration_min} />
                      )}
                      {canToggle && (
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={busy === s.day}
                          aria-label={`${dismissed ? "Restore" : "Dismiss"} ${dayLabel(s.day)}`}
                          onClick={() => toggleDismissed(s.day, dismissed)}
                        >
                          {dismissed ? "Restore" : "Dismiss"}
                        </Button>
                      )}
                      {!dismissed && !s.status.startsWith("done") && (
                        <SessionWeather day={s.day} onSwap={canToggle ? () => setSwapping({ day: s.day, type: s.session_type, minutes: s.duration_min }) : undefined} />
                      )}
                    </li>
                  )
                })}
              </ul>
            )}
            <WeekCompanions start={week.start} />
            {actionError && (
              <p role="alert" className="text-sm">
                Couldn’t change that session: {actionError}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {tool === "timeoff" && <PlanTimeOff onDone={() => { setTool(null); run() }} onCancel={() => setTool(null)} />}
      {tool === "race" && <PlanRace onDone={() => { setTool(null); setIndex(null); run() }} onCancel={() => setTool(null)} />}
      {tool === "availability" && (
        <PlanAvailability
          weekStart={week.start}
          today={today}
          stored={((plan as { availability?: Availability }).availability ?? {}) as Availability}
          onDone={() => { setTool(null); run() }}
          onCancel={() => setTool(null)}
        />
      )}
      {tool === "rematch" && <PlanRematch onDone={() => { setTool(null); run() }} onCancel={() => setTool(null)} />}
      {tool === "replace" && <PlanGenerate hasPlan onDone={() => { setTool(null); setIndex(null); run() }} />}
      {tool === null && (
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={() => setTool("timeoff")}>
            Time off…
          </Button>
          <Button variant="outline" size="sm" onClick={() => setTool("race")}>
            Add a race…
          </Button>
          <Button variant="outline" size="sm" onClick={() => setTool("availability")}>
            Availability…
          </Button>
          <Button variant="outline" size="sm" onClick={() => setTool("rematch")}>
            Match rides…
          </Button>
          {canUndoDeload && (
            <Button variant="outline" size="sm" disabled={busy === "deload"} onClick={undoDeload}>
              Undo the deload
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={() => setTool("replace")}>
            Replace the plan…
          </Button>
        </div>
      )}
    </div>
  )
}
