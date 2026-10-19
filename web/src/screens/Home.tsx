import { useState } from "react"

import type { PlanRead, ProgrammeSummary, RiderStats } from "@/api/types"
import {
  currentWeek,
  fmtMinutes,
  getPlan,
  getStats,
  getSummary,
  isoDay,
  plannedTss,
  reading,
  sessionsOn,
  weekSessions,
} from "@/lib/home"
import { Button } from "@/components/ui/button"
import { BodyPerf } from "@/screens/BodyPerf"
import { DfaSnapshotCard } from "@/screens/DfaSnapshot"
import { DailyCheckIn } from "@/screens/DailyCheckIn"
import { Glance } from "@/screens/Glance"
import { Hrv } from "@/screens/Hrv"
import { Panel, Row, useLoad } from "@/screens/panel"
import { AskCoach } from "@/screens/Coach"
import { Readiness } from "@/screens/Readiness"
import { Records } from "@/screens/Records"
import { LastWeek, ThisWeek } from "@/screens/WeekSummary"

const DETAILS_KEY = "home-details"
// ponytail: per-device, not per-rider; move under useShell().lsKey if riders share a device and disagree.
const savedDetails = () => {
  try {
    return localStorage.getItem(DETAILS_KEY) === "1"
  } catch {
    return false
  }
}

export function Home() {
  // On a phone Home is the "at a glance" answer plus the daily check-in; every other card is one tap away.
  // From md up the whole grid shows, as before.
  const [details, setDetails] = useState(savedDetails)
  const toggleDetails = () => {
    const next = !details
    setDetails(next)
    try {
      localStorage.setItem(DETAILS_KEY, next ? "1" : "0")
    } catch {
      /* private mode: the choice just isn't remembered */
    }
  }
  const [plan, retryPlan] = useLoad<PlanRead>(getPlan)
  const [stats, retryStats] = useLoad<RiderStats>(getStats)
  const [summary, retrySummary] = useLoad<ProgrammeSummary>(getSummary)
  const today = isoDay()

  return (
    <div className="grid gap-4 md:grid-cols-2" aria-label="Home">
      <Glance plan={plan} stats={stats} />

      <DailyCheckIn />

      <div className="md:hidden">
        <Button
          variant="outline"
          className="h-11 w-full"
          aria-expanded={details}
          aria-controls="home-details"
          onClick={toggleDetails}
        >
          {details ? "Show less" : "Show all details"}
        </Button>
      </div>

      <div
        id="home-details"
        className={details ? "contents" : "hidden md:contents"}
      >
        <Panel title="Today" load={plan} retry={retryPlan}>
          {(p) => {
            const week = currentWeek(p.plan_json, today)
            const todays = sessionsOn(week, today)
            if (!p.plan_json?.weeks?.length)
              return (
                <p className="text-sm text-muted-foreground">
                  No training plan yet. Create one in Training Plan.
                </p>
              )
            if (!todays.length)
              return <p className="text-sm">Rest day. Nothing planned today.</p>
            return (
              <ul className="space-y-2">
                {todays.map((s, i) => (
                  <li key={i} className="text-sm">
                    <span className="font-medium">
                      {s.zwo_name || s.session_type}
                    </span>
                    <span className="text-muted-foreground">
                      {" "}
                      · {fmtMinutes(s.duration_min)} ·{" "}
                      {Math.round(s.tss_estimate)} TSS
                      {s.status && s.status !== "pending"
                        ? ` · ${s.status.replace(/_/g, " ")}`
                        : ""}
                    </span>
                  </li>
                ))}
              </ul>
            )
          }}
        </Panel>

        <ThisWeek />

        <LastWeek />

        <Records />

        <DfaSnapshotCard />

        <Readiness />

        <AskCoach />

        <Hrv />

        <Panel title="This week" load={plan} retry={retryPlan}>
          {(p) => {
            const week = currentWeek(p.plan_json, today)
            const sessions = weekSessions(week)
            if (!week)
              return (
                <p className="text-sm text-muted-foreground">
                  No plan week covers today.
                </p>
              )
            return (
              <>
                <p className="text-sm text-muted-foreground">
                  {week.phase || "Plan"}
                  {week.is_stepback ? " · recovery week" : ""} ·{" "}
                  {plannedTss(sessions)} of {Math.round(week.tss_target)} TSS
                  planned
                </p>
                <ul className="space-y-1">
                  {sessions.map((s, i) => (
                    <li key={i} className="flex justify-between gap-4 text-sm">
                      <span
                        aria-current={s.day === today ? "date" : undefined}
                        className={s.day === today ? "font-medium" : ""}
                      >
                        {s.day_name || s.day} · {s.session_type}
                      </span>
                      <span className="text-muted-foreground">
                        {fmtMinutes(s.duration_min)}
                      </span>
                    </li>
                  ))}
                </ul>
              </>
            )
          }}
        </Panel>

        <Panel title="Fitness" load={stats} retry={retryStats}>
          {(s) => {
            const dash = (n: number | null, unit = "") =>
              n === null ? "—" : `${Math.round(n * 10) / 10}${unit}`
            const power = s.power as Record<string, unknown> | null | undefined
            const load = s.load as Record<string, unknown> | null | undefined
            return (
              <dl className="space-y-1">
                <Row label="FTP" value={dash(reading(power?.ftp), " W")} />
                <Row label="W/kg" value={dash(reading(power?.w_per_kg))} />
                <Row label="CTL (fitness)" value={dash(reading(load?.ctl))} />
                <Row label="ATL (fatigue)" value={dash(reading(load?.atl))} />
                <Row label="TSB (form)" value={dash(reading(load?.tsb))} />
              </dl>
            )
          }}
        </Panel>

        <div className="md:col-span-2">
          <BodyPerf />
        </div>

        <Panel title="Programme" load={summary} retry={retrySummary}>
          {(s) => (
            <dl className="space-y-1">
              <Row label="Weeks" value={s.weeks} />
              <Row label="Rides" value={s.rides} />
              <Row label="Hours" value={Number(s.totals?.hours ?? 0)} />
              <Row label="Distance" value={`${Number(s.totals?.km ?? 0)} km`} />
            </dl>
          )}
        </Panel>
      </div>
    </div>
  )
}
