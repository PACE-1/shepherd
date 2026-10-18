import { useEffect, useState, type ComponentType } from "react"

import type { IcuConnection, PlanRead, SettingsRead } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/native-select"
import { getLlm } from "@/lib/coach"
import { currentWeek, getPlan, isoDay, type Availability } from "@/lib/home"
import { aiCheck, goalCheck, icuCheck, locationCheck, riderCheck, riderPayload, TOUR } from "@/lib/onboarding"
import { getLocation } from "@/lib/weather"
import { LocationCard } from "@/screens/WeatherLocation"
import { diff, formFrom, getSettings, saveSettings, type RiderForm } from "@/lib/settings"
import { getIcuConnection, getLimits, type Limits } from "@/lib/setup"
import { ApiKeyConnect } from "@/screens/ApiKeyConnect"
import { AiCoachSettings } from "@/screens/Coach"
import { Folders } from "@/screens/Folders"
import { GoalEvent } from "@/screens/GoalEvent"
import { Panel, useLoad } from "@/screens/panel"
import { PlanAvailability } from "@/screens/PlanAvailability"
import { PlanGenerate } from "@/screens/PlanGenerate"

function IcuStep() {
  const [load, retry] = useLoad<IcuConnection>(getIcuConnection)
  return (
    <Panel title="intervals.icu" load={load} retry={retry}>
      {(c) => (
        <div className="space-y-2 text-sm">
          <p>{c.connected ? `Connected${c.name ? ` as ${c.name}` : ""}.` : "Not connected yet."}</p>
          {!c.connected && <ApiKeyConnect onConnected={retry} />}
        </div>
      )}
    </Panel>
  )
}

const HELP = {
  ftp: "FTP is the most power you could hold for about an hour. Not sure? Keep the estimate and test later.",
  lthr: "LTHR is the heart rate you could hold for about an hour of hard riding.",
  maxHr: "Max HR is the highest heart rate you have seen on a hard effort.",
} as const

function RiderFields({ s, limits }: { s: SettingsRead; limits: Limits }) {
  const [f, setF] = useState<RiderForm>(() => formFrom(s))
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState("")
  const { problems } = diff(s, f, limits)
  const set = (k: keyof RiderForm, v: string) => {
    setSaved(false)
    setF({ ...f, [k]: v } as RiderForm)
  }
  const save = async () => {
    setBusy(true)
    setError("")
    try {
      await saveSettings(riderPayload(f))
      setSaved(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }
  const field = (k: "weight" | "ftp" | "lthr" | "maxHr", label: string) => (
    <Label className="flex-col items-start gap-1">
      {label}
      <Input type="number" className="w-28" value={f[k]} onChange={(e) => set(k, e.target.value)} />
    </Label>
  )
  return (
    <div className="space-y-3 text-sm">
      <div className="flex flex-wrap items-end gap-3">
        {field("weight", "Weight (kg)")}
        {field("ftp", "FTP (W)")}
        {field("lthr", "LTHR (bpm)")}
        {field("maxHr", "Max HR (bpm)")}
        <Label className="flex-col items-start gap-1">
          Targets
          <NativeSelect value={f.targetMode} onChange={(e) => set("targetMode", e.target.value)}>
            <option value="power">Power</option>
            <option value="hr">Heart rate</option>
          </NativeSelect>
        </Label>
      </div>
      <ul className="list-disc space-y-0.5 pl-5 text-muted-foreground">
        <li>{HELP.ftp}</li>
        <li>{HELP.lthr}</li>
        <li>{HELP.maxHr}</li>
      </ul>
      {problems.map((p) => (
        <p key={p} role="alert">{p}</p>
      ))}
      <Button size="sm" disabled={busy || problems.length > 0} onClick={save}>
        {busy ? "Saving…" : "Save rider numbers"}
      </Button>
      {saved && <p role="status">Saved.</p>}
      {error && <p role="alert">Couldn’t save: {error}</p>}
    </div>
  )
}

function RiderStep() {
  const [load, retry] = useLoad<SettingsRead>(getSettings)
  const [limits, setLimits] = useState<Limits>({})
  useEffect(() => { getLimits().then(setLimits, () => {}) }, [])
  return (
    <Panel title="Rider numbers" load={load} retry={retry}>
      {(s) => <RiderFields s={s} limits={limits} />}
    </Panel>
  )
}

function GoalStep() {
  const [load, retry] = useLoad<PlanRead>(getPlan)
  const [setting, setSetting] = useState(false)
  const [message, setMessage] = useState("")
  return (
    <Panel title="Your plan" load={load} retry={retry}>
      {(p) => {
        const weeks = p.plan_json?.weeks ?? []
        if (!weeks.length)
          return (
            <div className="space-y-2 text-sm">
              <p>Pick a goal and how many hours a week you can ride. Choose “Event” to aim at a race or ride on a date.</p>
              <PlanGenerate hasPlan={false} onDone={retry} />
            </div>
          )
        const week = currentWeek(p.plan_json, isoDay()) ?? weeks[0]
        return (
          <div className="space-y-3 text-sm">
            <GoalEvent />
            <p className="text-muted-foreground">Your plan is ready: {weeks.length} weeks. Now say which days you can ride.</p>
            {setting ? (
              <PlanAvailability
                weekStart={week.start}
                today={isoDay()}
                stored={((p as { availability?: Availability }).availability ?? {}) as Availability}
                onDone={() => { setSetting(false); setMessage("Availability saved. Your plan was adjusted."); retry() }}
                onCancel={() => setSetting(false)}
              />
            ) : (
              <Button size="sm" variant="outline" onClick={() => setSetting(true)}>
                Set this week’s availability
              </Button>
            )}
            {message && <p role="status">{message}</p>}
          </div>
        )
      }}
    </Panel>
  )
}

function TourStep() {
  return (
    <ul className="space-y-2 text-sm">
      {TOUR.map((t) => (
        <li key={t.name}>
          <a className="font-medium underline" href={t.href}>{t.name}</a>
          <span className="text-muted-foreground"> · {t.text}</span>
        </li>
      ))}
    </ul>
  )
}

export const BODIES: Record<string, ComponentType> = {
  icu: IcuStep,
  rider: RiderStep,
  ai: AiCoachSettings,
  folders: Folders,
  location: () => <LocationCard title="Your location" />,
  goal: GoalStep,
  tour: TourStep,
}

/** Each check reads the server, so "Continue" moves on only when the step really is complete. */
export const CHECKS: Record<string, () => Promise<string | null>> = {
  icu: async () => icuCheck(await getIcuConnection()),
  rider: async () => riderCheck(await getSettings()),
  ai: async () => aiCheck(await getLlm()),
  location: async () => locationCheck(await getLocation()),
  goal: async () => goalCheck(await getPlan()),
}
