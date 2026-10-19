import { useEffect, useRef, useState } from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { IcuComparison, LinkedCard, StepDots } from "@/components/wizard"
import { icuLinkFailureText } from "@/lib/icuReasons"
import {
  COLORS,
  DEFAULTS,
  ICU_RETURN_TO,
  activateProfile,
  buildSavePayload,
  clearWizard,
  createProfile,
  getIcuConnection,
  getLimits,
  readWizard,
  saveSetup,
  stashWizard,
  type FieldKey,
  type IcuConnection,
  type Limits,
  type TargetMode,
} from "@/lib/setup"

const NUMBER_FIELDS: { key: FieldKey; label: string; limit: keyof Limits; min: number; max: number; step?: number }[] = [
  { key: "ftp", label: "FTP (watts)", limit: "ftp", min: 50, max: 600 },
  { key: "weight", label: "Weight (kg)", limit: "weight", min: 30, max: 200, step: 0.1 },
  { key: "lthr", label: "LTHR (bpm)", limit: "lthr", min: 100, max: 220 },
  { key: "max-hr", label: "Max HR (bpm)", limit: "max_hr", min: 140, max: 220 },
  { key: "age", label: "Age (years)", limit: "age", min: 10, max: 100 },
]

type LinkState = "unlinked" | "linked" | "error"

export function ProfileSetup() {
  const [step, setStep] = useState<1 | 2 | 3>(() => (readWizard() ? 3 : 1))
  const [name, setName] = useState("")
  const [color, setColor] = useState(COLORS[0])
  const [values, setValues] = useState(DEFAULTS)
  const [touched, setTouched] = useState<ReadonlySet<FieldKey>>(new Set())
  const [targetMode, setTargetMode] = useState<TargetMode>("power")
  const [targetModeTouched, setTargetModeTouched] = useState(false)
  const [limits, setLimits] = useState<Limits>({})
  const [status, setStatus] = useState<{ text: string; ok: boolean } | null>(null)
  const [busy, setBusy] = useState(false)
  // Returning from the intervals.icu OAuth round-trip: ?icu=ok|error|unavailable[&reason=&status=].
  const [returned] = useState(() => {
    const q = new URLSearchParams(window.location.search)
    const icu = q.get("icu")
    return icu ? { icu, reason: q.get("reason") ?? "", status: q.get("status") ?? "" } : null
  })
  const linkFailed = returned?.icu === "error" || returned?.icu === "unavailable"
  const linkError = linkFailed ? icuLinkFailureText(returned.reason, returned.status) : ""
  const [linked, setLinked] = useState(false)
  const linkState: LinkState = linked ? "linked" : linkFailed ? "error" : "unlinked"
  const [connection, setConnection] = useState<IcuConnection | null>(null)
  // Set only after a successful create, so a retry never makes a second profile.
  const createdId = useRef<string | null>(readWizard())

  useEffect(() => {
    getLimits().then(setLimits).catch(() => {})
  }, [])

  useEffect(() => {
    if (!returned) return
    clearWizard()
    window.history.replaceState({}, "", "/v2/#/profile-setup")
    if (linkFailed) return
    getIcuConnection()
      .then((c) => {
        if (c?.method === "oauth") {
          setConnection(c)
          setLinked(true)
        }
      })
      .catch(() => {})
  }, [returned, linkFailed])

  const setField = (key: FieldKey, value: string) => {
    setValues((v) => ({ ...v, [key]: value }))
    setTouched((t) => new Set(t).add(key))
  }
  const pickMode = (mode: TargetMode) => {
    setTargetMode(mode)
    setTargetModeTouched(true)
  }

  const next = () => {
    if (!name.trim()) return setStatus({ text: "Please enter a name.", ok: false })
    setStatus(null)
    setStep(2)
  }

  // One server interaction, at the end: create -> activate (checked) -> save touched fields.
  const finish = async () => {
    if (busy) return
    if (!name.trim()) {
      setStatus({ text: "Please enter a name.", ok: false })
      return setStep(1)
    }
    if (targetModeTouched && targetMode === "hr" && !touched.has("lthr")) {
      return setStatus({ text: "Heart-rate mode needs your LTHR — fill in the LTHR field.", ok: false })
    }
    setBusy(true)
    setStatus(null)
    try {
      let warning: string | undefined
      if (!createdId.current) {
        let created
        try {
          created = await createProfile(name.trim(), color)
        } catch (e) {
          return setStatus({ text: (e as Error).message || "Failed to create profile.", ok: false })
        }
        if (!created.id) return setStatus({ text: "Failed to create profile.", ok: false })
        createdId.current = created.id
        warning = created.warning
      }
      try {
        const sw = await activateProfile(createdId.current)
        if (sw.active !== createdId.current) throw new Error("")
      } catch (e) {
        const detail = (e as Error).message
        return setStatus({
          text: `Could not activate the new profile${detail ? ` — ${detail}` : ""}. Try again.`,
          ok: false,
        })
      }
      try {
        await saveSetup(buildSavePayload(values, touched, targetMode, targetModeTouched))
      } catch (e) {
        return setStatus({ text: (e as Error).message || "Save failed.", ok: false })
      }
      setStatus(warning ? { text: warning, ok: true } : null)
      setStep(3)
    } finally {
      setBusy(false)
    }
  }

  const connect = () => {
    if (createdId.current) stashWizard(createdId.current)
    window.location.href = `/oauth/icu/start?return_to=${encodeURIComponent(ICU_RETURN_TO)}`
  }

  return (
    <div className="mx-auto flex min-h-svh max-w-3xl flex-col justify-center px-6 py-12">
      <h1 className="text-center text-3xl font-semibold tracking-tight">Shepherd</h1>
      <p className="mb-4 text-center text-muted-foreground">Set up a new rider profile in 3 steps.</p>
      <StepDots step={step} total={3} />
      <Card className="[--card-spacing:--spacing(8)]">
        <CardContent className="grid gap-6">
          {step === 1 && (
            <>
              <h2 className="text-lg font-semibold">Name &amp; Color</h2>
              <div className="grid gap-2">
                <Label htmlFor="profile-name">Display Name</Label>
                <Input
                  id="profile-name"
                  autoFocus
                  autoComplete="off"
                  placeholder="e.g. Anna"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </div>
              <div className="grid gap-2">
                <Label>Profile Color</Label>
                <div className="flex flex-wrap gap-2">
                  {COLORS.map((c) => (
                    <button
                      key={c}
                      type="button"
                      aria-label={`Color ${c}`}
                      aria-pressed={c === color}
                      className="size-8 rounded-full ring-offset-2 ring-offset-background aria-pressed:ring-2 aria-pressed:ring-foreground"
                      style={{ background: c }}
                      onClick={() => setColor(c)}
                    />
                  ))}
                </div>
              </div>
              <Status status={status} />
              <div className="flex justify-between">
                <Button variant="ghost" render={<a href="/" />}>Cancel</Button>
                <Button onClick={next}>Next</Button>
              </div>
            </>
          )}
          {step === 2 && (
            <>
              <h2 className="text-lg font-semibold">Athlete Numbers</h2>
              <p className="text-sm text-muted-foreground">
                Set your current fitness values. You can update these anytime in Settings — fields you
                leave untouched simply aren't written.
              </p>
              <div className="grid gap-2">
                <Label>How do you train?</Label>
                <div className="flex gap-2">
                  <Button variant={targetMode === "power" ? "default" : "outline"} onClick={() => pickMode("power")}>
                    Power meter
                  </Button>
                  <Button variant={targetMode === "hr" ? "default" : "outline"} onClick={() => pickMode("hr")}>
                    Heart rate only
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">
                  Heart-rate mode prescribes workout targets from your LTHR — the LTHR field below is required.
                </p>
              </div>
              <div className="grid gap-x-6 gap-y-5 sm:grid-cols-2">
                {NUMBER_FIELDS.map((f) => (
                  <div key={f.key} className="grid gap-2">
                    <Label htmlFor={f.key}>{f.label}</Label>
                    <Input
                      id={f.key}
                      type="number"
                      min={limits[f.limit]?.[0] ?? f.min}
                      max={limits[f.limit]?.[1] ?? f.max}
                      step={f.step}
                      placeholder={f.key === "age" ? "35" : undefined}
                      value={values[f.key]}
                      onChange={(e) => setField(f.key, e.target.value)}
                    />
                  </div>
                ))}
                <div className="grid gap-2">
                  <Label htmlFor="sex">Sex</Label>
                  {/* ponytail: native select; swap for the shadcn Select when a second one appears */}
                  <select
                    id="sex"
                    className="h-9 rounded-lg border border-input bg-background px-3 text-sm dark:bg-input/30"
                    value={values.sex}
                    onChange={(e) => setField("sex", e.target.value)}
                  >
                    <option value="">Prefer not to say</option>
                    <option value="M">Male</option>
                    <option value="F">Female</option>
                    <option value="O">Other</option>
                  </select>
                </div>
              </div>
              <details>
                <summary className="cursor-pointer text-sm text-muted-foreground">Advanced (optional)</summary>
                <div className="mt-3 grid gap-4">
                  <div className="grid gap-2">
                    <Label htmlFor="cp">Critical Power (W) — defaults to FTP × 1.03 if blank</Label>
                    <Input id="cp" type="number" placeholder="auto" value={values.cp} onChange={(e) => setField("cp", e.target.value)} />
                  </div>
                  <div className="grid gap-2">
                    <Label htmlFor="wprime">W' — anaerobic capacity (J) — defaults to FTP × 80</Label>
                    <Input id="wprime" type="number" placeholder="auto" value={values.wprime} onChange={(e) => setField("wprime", e.target.value)} />
                  </div>
                </div>
              </details>
              <Status status={status} />
              <div className="flex justify-between">
                <Button variant="outline" onClick={() => setStep(1)}>Back</Button>
                <Button disabled={busy} onClick={finish}>Create profile</Button>
              </div>
            </>
          )}
          {step === 3 && (
            <>
              <h2 className="text-lg font-semibold">Your training data</h2>
              <p className="text-sm text-muted-foreground">
                Profile created ✓. Shepherd plans from what you actually ride. It can read that from{" "}
                <a className="underline" href="https://intervals.icu/" target="_blank" rel="noopener noreferrer">
                  intervals.icu
                </a>
                , a free training-analysis service, or from ride files you import yourself.
              </p>
              {linkState !== "linked" && (
                <>
                  <IcuComparison />
                </>
              )}
              <div role="status" aria-live="polite" className="min-h-5 text-sm">
                {linkState === "error" && (
                  <span className="text-destructive">Couldn’t link your account — {linkError}</span>
                )}
                {linkState === "linked" && (
                  <LinkedCard connection={connection} next="Your fitness, fatigue and recent rides come in when you finish." />
                )}
              </div>
              <Status status={status} />
              <div className="flex flex-wrap items-center gap-2">
                {linkState === "linked" ? (
                  <>
                    <Button render={<a href="/" />}>Finish setup</Button>
                    <Button variant="outline" size="sm" onClick={connect}>Use a different account</Button>
                  </>
                ) : (
                  <>
                    <Button onClick={connect}>{linkState === "error" ? "Try again" : "Sign in to intervals.icu"}</Button>
                    <Button
                      variant="outline"
                      className="max-md:min-h-11"
                      render={<a href="https://intervals.icu/signup" target="_blank" rel="noopener noreferrer" />}
                    >
                      Create a free account
                    </Button>
                    <Button
                      variant="ghost"
                      render={<a href="/" title="Import your ride files yourself; connect intervals.icu any time in Settings" />}
                    >
                      Continue without intervals.icu →
                    </Button>
                  </>
                )}
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function Status({ status }: { status: { text: string; ok: boolean } | null }) {
  if (!status) return null
  return (
    <p role={status.ok ? "status" : "alert"} className={`text-sm ${status.ok ? "text-primary" : "text-destructive"}`}>
      {status.text}
    </p>
  )
}
