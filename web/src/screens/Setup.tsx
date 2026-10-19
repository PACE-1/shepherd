import { useEffect, useMemo, useRef, useState } from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/native-select"
import { IcuComparison, LinkedCard, StepDots } from "@/components/wizard"
import {
  FIELD_IDS,
  INITIAL,
  LS_KEY,
  allValid,
  bounds,
  buildPayload,
  checkActivities,
  ensureProfile,
  fieldError,
  getAthleteNumbers,
  getDefaults,
  pickFolder,
  restore,
  serialize,
  toggleDay,
  toggleRest,
  type FieldId,
  type WizardState,
} from "@/lib/firstRun"
import { ApiKeyConnect } from "@/screens/ApiKeyConnect"
import { icuLinkFailureText } from "@/lib/icuReasons"
import { getIcuConnection, getLimits, saveSetup, type IcuConnection, type Limits } from "@/lib/setup"
import type { WeatherPlace } from "@/api/types"
import { placeLabel, saveLocation } from "@/lib/weather"
import { PlaceSearch } from "@/screens/WeatherLocation"

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
type Link = "unlinked" | "linked" | "error"
type Msg = { text: string; ok: boolean } | null

export function Setup() {
  const [step, setStep] = useState(1)
  const [s, setS] = useState<WizardState>(INITIAL)
  const [limits, setLimits] = useState<Limits>({})
  // Returning from the intervals.icu OAuth round trip: ?icu=ok|error|unavailable[&reason=&status=].
  const [returned] = useState(() => {
    const q = new URLSearchParams(window.location.search)
    const icu = q.get("icu")
    return icu ? { icu, reason: q.get("reason") ?? "", status: q.get("status") ?? "" } : null
  })
  const returnFailed = returned?.icu === "error" || returned?.icu === "unavailable"
  const [link, setLink] = useState<Link>(returnFailed ? "error" : "unlinked")
  const [linkMsg, setLinkMsg] = useState(returnFailed ? icuLinkFailureText(returned.reason, returned.status) : "")
  const [connection, setConnection] = useState<IcuConnection | null>(null)
  const [oauthAvailable, setOauthAvailable] = useState(true)
  const [connected, setConnected] = useState(false)
  const [autofill, setAutofill] = useState("")
  const [garmin, setGarmin] = useState<Msg>(null)
  const [saveMsg, setSaveMsg] = useState<Msg>(null)
  const [saving, setSaving] = useState(false)
  const [place, setPlace] = useState<WeatherPlace | null>(null)   // kept in memory only, saved to the profile at the end
  const ready = useRef(false)

  // Persist after the first restore so a reload (or the OAuth round trip) keeps the rider's entries.
  useEffect(() => {
    if (!ready.current) return
    try {
      localStorage.setItem(LS_KEY, JSON.stringify(serialize(s)))
    } catch {
      /* private mode */
    }
  }, [s])

  useEffect(() => {
    if (returned) window.history.replaceState({}, "", "/v2/#/setup")
    const ctrl = new AbortController()
    const timer = setTimeout(() => ctrl.abort(), 5000)
    getLimits().then(setLimits).catch(() => {})
    ;(async () => {
      let base = INITIAL
      try {
        const d = await getDefaults(ctrl.signal)
        const values = { ...base.values }
        const touched: FieldId[] = []
        if (d.workout_dir) { values["s-workout-dir"] = d.workout_dir; touched.push("s-workout-dir") }
        if (d.weight) values["s-weight"] = String(d.weight)
        if (d.ftp) values["s-ftp"] = String(d.ftp)
        if (d.lthr) values["s-lthr"] = String(d.lthr)
        if (d.max_hr) values["s-maxhr"] = String(d.max_hr)
        base = { ...base, values, touched }
      } catch {
        /* offline: keep static defaults */
      } finally {
        clearTimeout(timer)
      }
      let saved: Record<string, unknown> | null
      try {
        saved = JSON.parse(localStorage.getItem(LS_KEY) || "null")
      } catch {
        saved = null
      }
      // Anything typed while the defaults were loading wins over the restored values.
      setS((cur) => {
        const r = restore(base, saved)
        if (!cur.touched.length) return r
        return {
          ...r,
          values: { ...r.values, ...Object.fromEntries(cur.touched.map((id) => [id, cur.values[id]])) },
          touched: [...new Set([...r.touched, ...cur.touched])],
        }
      })
      ready.current = true
    })()
    if (returnFailed) return () => ctrl.abort()
    getIcuConnection()
      .then((c) => {
        if (c && c.oauth_available === false) setOauthAvailable(false)
        if (c?.method === "oauth") {
          setConnection(c)
          setLink("linked")
        }
        if (c && (c.method === "oauth" || c.method === "apikey" || (c as { connected?: boolean }).connected)) {
          setConnected(true)
        }
      })
      .catch(() => {})
    return () => ctrl.abort()
  }, [returned, returnFailed])

  const errors = useMemo(
    () => Object.fromEntries(FIELD_IDS.map((id) => [id, fieldError(id, s.values, limits)])) as Record<FieldId, string>,
    [s.values, limits],
  )
  const valid = allValid(s.values, limits)

  const setField = (id: FieldId, value: string) =>
    setS((p) => ({
      ...p,
      values: { ...p.values, [id]: value },
      touched: p.touched.includes(id) ? p.touched : [...p.touched, id],
      icuOrigin: p.icuOrigin.filter((x) => x !== id),
    }))

  const doAutofill = async () => {
    setAutofill("Fetching from intervals.icu…")
    try {
      const a = await getAthleteNumbers()
      const map: [keyof typeof a, FieldId, string][] = [
        ["ftp", "s-ftp", "ftp"], ["weight", "s-weight", "weight"], ["lthr", "s-lthr", "lthr"], ["max_hr", "s-maxhr", "max hr"],
      ]
      const found = a?.ok ? map.filter(([k]) => a[k] != null && a[k] !== ("" as unknown)) : []
      setS((p) => {
        const values = { ...p.values }
        const touched = new Set(p.touched)
        const origin = new Set(p.icuOrigin)
        for (const [k, id] of found) {
          values[id] = String(a[k])
          touched.add(id)
          origin.add(id)
        }
        return { ...p, values, touched: [...touched], icuOrigin: [...origin] }
      })
      setAutofill(
        found.length
          ? `Filled from intervals.icu: ${found.map(([, , label]) => label).join(", ")} — edit anything that looks off.`
          : a?.ok
            ? "intervals.icu has no FTP, weight or heart-rate numbers for you yet. Enter them below."
            : "Couldn’t read your numbers from intervals.icu. Check the connection in step 1, or enter them below.",
      )
    } catch {
      setAutofill("Auto-fill failed — enter your numbers manually.")
    }
  }

  const doGarmin = async () => {
    setGarmin({ text: "Checking Intervals.icu for recent activities...", ok: true })
    try {
      const d = await checkActivities()
      if (!d.ok) return setGarmin({ text: d.error || "Check failed.", ok: false })
      if ((d.count ?? 0) > 0) {
        setGarmin({
          text:
            `✓ ${d.count} recent activit${d.count === 1 ? "y" : "ies"} on Intervals.icu` +
            (d.garmin_count ? ` (${d.garmin_count} from Garmin)` : "") +
            (d.latest_date ? ` · latest ${d.latest_date}` : "") + ".",
          ok: true,
        })
      } else {
        setGarmin({
          text: "No activities in the last 6 weeks yet. Connect your device or app above and ride — new rides can take a few minutes to sync.",
          ok: true,
        })
      }
    } catch (e) {
      setGarmin({ text: `Check failed: ${(e as Error).message}`, ok: false })
    }
  }

  const connect = async () => {
    const ok = await ensureProfile()
    if (ok === 409) return void (window.location.href = "/profile-picker")
    if (ok !== true) {
      setLinkMsg(icuLinkFailureText(ok === 503 ? "busy" : "", ""))
      return setLink("error")
    }
    window.location.href = `/oauth/icu/start?return_to=${encodeURIComponent("/v2/?wizard=setup")}`
  }

  const browse = async (id: FieldId) => {
    try {
      const d = await pickFolder()
      if (d.path) setField(id, d.path)
    } catch {
      /* picker unavailable (browser mode) */
    }
  }

  const save = async () => {
    if (saving) return
    if (s.targetModeTouched && s.targetMode === "hr" && !s.touched.includes("s-lthr")) {
      setSaveMsg({ text: "Heart-rate mode needs your LTHR — fill in the LTHR field on the Profile step.", ok: false })
      return setStep(2)
    }
    if (!valid) return
    setSaving(true)
    setSaveMsg(null)
    try {
      const ens = await ensureProfile()
      if (ens !== true) {
        return setSaveMsg({
          text: ens === 503 ? "A sync is running — try again in a moment." : "Could not create your profile — please try again.",
          ok: false,
        })
      }
      try {
        await saveSetup(buildPayload(s) as Record<string, number | string>)
      } catch (e) {
        return setSaveMsg({ text: (e as Error).message || "Save failed.", ok: false })
      }
      if (place) await saveLocation(place).catch(() => {})   // optional: setup is complete without it
      setSaveMsg({ text: "Setup complete! Redirecting to dashboard...", ok: true })
      try {
        localStorage.removeItem(LS_KEY)
      } catch {
        /* ignore */
      }
      setTimeout(() => window.location.assign("/"), 1500)
    } finally {
      setSaving(false)
    }
  }

  const num = (id: FieldId, label: string, opts: { hint?: string; icu?: boolean; step?: number; placeholder?: string } = {}) => {
    const { min, max } = bounds(id, limits)
    return (
      <div className="grid gap-1.5">
        <Label htmlFor={id}>
          {label}
          {opts.icu && s.icuOrigin.includes(id) && (
            <span className="ml-2 rounded bg-muted px-1.5 py-0.5 text-xs">from intervals.icu</span>
          )}
        </Label>
        <Input
          id={id}
          type="number"
          min={min}
          max={max}
          step={opts.step ?? 1}
          placeholder={opts.placeholder}
          aria-invalid={!!errors[id]}
          value={s.values[id]}
          onChange={(e) => setField(id, e.target.value)}
        />
        {errors[id] ? (
          <p role="alert" className="text-xs text-destructive">{errors[id]}</p>
        ) : (
          opts.hint && <p className="text-xs text-muted-foreground">{opts.hint}</p>
        )}
      </div>
    )
  }

  return (
    <div className="mx-auto flex min-h-svh max-w-3xl flex-col justify-center px-6 py-12">
      <h1 className="text-center text-3xl font-semibold tracking-tight">Shepherd</h1>
      <p className="mb-4 text-center text-muted-foreground">Let's get you set up in 4 quick steps.</p>
      <StepDots step={step} total={4} />
      <Card className="[--card-spacing:--spacing(8)]">
        <CardContent className="grid gap-6">
          {step === 1 && (
            <>
              <h2 className="text-lg font-semibold">Your training data</h2>
              <p className="text-sm text-muted-foreground">
                Shepherd plans from what you actually ride. It can read that from{" "}
                <a className="underline" href="https://intervals.icu/" target="_blank" rel="noopener noreferrer">intervals.icu</a>
                , a free training-analysis service, or from ride files you import yourself.
              </p>
              {link !== "linked" && <IcuComparison />}
              <div role="status" aria-live="polite" className="min-h-5 text-sm">
                {link === "error" && <span className="text-destructive">Couldn’t link your account — {linkMsg}</span>}
                {link === "linked" && (
                  <LinkedCard connection={connection} next="Your fitness and rides come in once the setup is complete." />
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                {link === "linked" ? (
                  <Button variant="outline" size="sm" onClick={connect}>Use a different account</Button>
                ) : (
                  <>
                    {oauthAvailable && <Button onClick={connect}>{link === "error" ? "Try again" : "Sign in to intervals.icu"}</Button>}
                    <ApiKeyConnect
                      open={!oauthAvailable}
                      prepare={async () => (await ensureProfile()) === true}
                      onConnected={() =>
                        getIcuConnection().then((c) => {
                          setConnection(c)
                          setLink("linked")
                          setConnected(true)
                        }, () => {})
                      }
                    />
                    <Button variant="outline" className="max-md:min-h-11" render={<a href="https://intervals.icu/signup" target="_blank" rel="noopener noreferrer" />}>
                      Create a free account
                    </Button>
                  </>
                )}
              </div>
              {connected && (
                <div className="grid gap-2 border-t pt-4">
                  <h3 className="font-semibold">3 · Get your rides into Intervals.icu</h3>
                  <p className="text-sm text-muted-foreground">
                    So new rides appear in your plan automatically, connect the device or app you record with to
                    Intervals.icu (one-time):
                  </p>
                  <ol className="list-decimal pl-5 text-sm">
                    <li>
                      Open{" "}
                      <a className="underline" href="https://intervals.icu/settings" target="_blank" rel="noopener noreferrer">
                        intervals.icu/settings
                      </a>{" "}
                      → <b>Connections</b>
                    </li>
                    <li>Pick the service your rides are recorded with (your bike computer, watch or training app) → authorise</li>
                  </ol>
                  <p className="text-xs text-muted-foreground">
                    New rides can take a few minutes to appear. Without a connection, or if rides stop arriving, you can
                    import FIT files instead: one at a time on the Analysis tab, or a whole folder in Settings (Folder import).
                  </p>
                  <Button variant="outline" className="w-fit" onClick={doGarmin}>Check sync</Button>
                  {garmin && <p role="status" className={`text-sm ${garmin.ok ? "" : "text-destructive"}`}>{garmin.text}</p>}
                </div>
              )}
              <div className="flex justify-end">
                <Button variant={link === "linked" ? "default" : "outline"} onClick={() => setStep(2)}>
                  {link === "linked" ? "Continue" : "Continue without intervals.icu"}
                </Button>
              </div>
            </>
          )}
          {step === 2 && (
            <>
              <h2 className="text-lg font-semibold">Your Profile</h2>
              <p className="text-sm text-muted-foreground">
                These values power your training zones. If you connected Intervals.icu, auto-fill pulls them from your data.
              </p>
              {connected && (
                <div>
                  <Button variant="outline" onClick={doAutofill}>Auto-fill from your data</Button>
                  {autofill && <p className="mt-1.5 text-xs text-muted-foreground">{autofill}</p>}
                </div>
              )}
              <div className="grid gap-2">
                <Label>How do you train?</Label>
                <div className="flex gap-2">
                  <Button size="sm" variant={s.targetMode === "power" ? "default" : "outline"}
                    onClick={() => setS((p) => ({ ...p, targetMode: "power", targetModeTouched: true }))}>
                    Power meter
                  </Button>
                  <Button size="sm" variant={s.targetMode === "hr" ? "default" : "outline"}
                    onClick={() => setS((p) => ({ ...p, targetMode: "hr", targetModeTouched: true }))}>
                    Heart rate only
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">
                  Heart-rate mode prescribes workout targets from your LTHR — the LTHR field below is required.
                </p>
              </div>
              <div className="grid gap-x-6 gap-y-5 sm:grid-cols-2">
                {num("s-weight", "Weight (kg)", { icu: true, step: 0.1, hint: "Used for W/kg and climb power estimates" })}
                {num("s-ftp", "FTP — Functional Threshold Power (watts)", { icu: true, hint: "The max power you can sustain for ~1 hour" })}
                {num("s-lthr", "LTHR — Lactate Threshold Heart Rate (bpm)", { icu: true, hint: "Tip: your average HR during a 30min all-out effort is a good estimate" })}
                {num("s-maxhr", "Max Heart Rate (bpm)", { icu: true, hint: "Formula estimates (220-age) are unreliable. Use your actual recorded max if known." })}
                {num("s-age", "Age (years) (optional)", { placeholder: "35" })}
                <div className="grid gap-1.5">
                  <Label htmlFor="s-sex">Sex (optional)</Label>
                  <NativeSelect id="s-sex"
                    value={s.values["s-sex"]} onChange={(e) => setField("s-sex", e.target.value)}>
                    <option value="">Prefer not to say</option>
                    <option value="M">Male</option>
                    <option value="F">Female</option>
                    <option value="O">Other</option>
                  </NativeSelect>
                </div>
              </div>
              <details>
                <summary className="cursor-pointer text-sm text-muted-foreground">Advanced (optional)</summary>
                <div className="mt-3 grid gap-4">
                  {num("s-cp", "Critical Power (W) — defaults to FTP × 1.03 if blank", { placeholder: "auto" })}
                  {num("s-wprime", "W' — anaerobic capacity (J) — defaults to FTP × 80", { placeholder: "auto", step: 100 })}
                </div>
              </details>
              <div className="flex justify-between">
                <Button variant="outline" onClick={() => setStep(1)}>Back</Button>
                <Button disabled={!valid} onClick={() => setStep(3)}>Next</Button>
              </div>
            </>
          )}
          {step === 3 && (
            <>
              <h2 className="text-lg font-semibold">Workout &amp; Route Folders</h2>
              <p className="text-sm text-muted-foreground">
                Shepherd comes with a full <b>workout library built in</b>, which is always used, so you can leave
                the folder empty. If you keep your own workout files on this computer, add that folder: its workouts
                join the built-in library. Click <b>Browse</b> to pick one. You can change this anytime in <b>Settings</b>.
              </p>
              {([
                ["s-workout-dir", "Extra workouts folder (optional)", "~/Documents/Workouts", "Your own structured workout files (.zwo); they are added to the built-in library"],
              ] as [FieldId, string, string, string][]).map(([id, label, ph, hint]) => (
                <div key={id} className="grid gap-1.5">
                  <Label htmlFor={id}>{label}</Label>
                  <div className="flex gap-2">
                    <Input id={id} placeholder={ph} value={s.values[id]} onChange={(e) => setField(id, e.target.value)} />
                    <Button variant="outline" onClick={() => browse(id)}>Browse</Button>
                  </div>
                  <p className="text-xs text-muted-foreground">{hint}</p>
                </div>
              ))}
              <p className="text-sm text-muted-foreground">
                <b>Almost done.</b> One more step — your weekly hours and training days. When you finish, Shepherd
                opens your dashboard, pulls in your recent training from intervals.icu (if you connected it), and you
                can generate your first training plan with one click.
              </p>
              <div className="flex justify-between">
                <Button variant="outline" onClick={() => setStep(2)}>Back</Button>
                <Button onClick={() => setStep(4)}>Next</Button>
              </div>
            </>
          )}
          {step === 4 && (
            <>
              <h2 className="text-lg font-semibold">Training Preferences</h2>
              {num("s-hours", "Hours per week", { step: 0.5 })}
              <DayGrid label="Training days (click to toggle)" on={s.days} onToggle={(d) => setS((p) => toggleDay(p, d))} />
              <DayGrid label="Rest days (click to mark)" on={s.rest} onToggle={(d) => setS((p) => toggleRest(p, d))} />
              <div className="grid gap-2">
                <Label>Where do you ride? (optional)</Label>
                <p className="text-sm text-muted-foreground">
                  For the weather forecast next to your outdoor sessions. Skip it and the forecast stays off; you can add it later in Settings.
                </p>
                {place && (
                  <p className="text-sm">
                    Riding near <b>{placeLabel(place)}</b>.{" "}
                    <Button size="sm" variant="ghost" onClick={() => setPlace(null)}>Use no location</Button>
                  </p>
                )}
                <PlaceSearch onPick={setPlace} />
              </div>
              {saveMsg && (
                <p role={saveMsg.ok ? "status" : "alert"} className={`text-sm ${saveMsg.ok ? "text-primary" : "text-destructive"}`}>
                  {saveMsg.text}
                </p>
              )}
              <div className="flex justify-between">
                <Button variant="outline" onClick={() => setStep(3)}>Back</Button>
                <Button disabled={!valid || saving} onClick={save}>
                  {saving ? "Saving..." : "Complete Setup"}
                </Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function DayGrid({ label, on, onToggle }: { label: string; on: string[]; onToggle: (day: string) => void }) {
  return (
    <div className="grid gap-2">
      <Label>{label}</Label>
      <div className="grid grid-cols-7 gap-1.5">
        {DAYS.map((name, i) => (
          <Button
            key={name}
            size="sm"
            variant={on.includes(String(i)) ? "default" : "outline"}
            aria-pressed={on.includes(String(i))}
            onClick={() => onToggle(String(i))}
          >
            {name}
          </Button>
        ))}
      </div>
    </div>
  )
}
