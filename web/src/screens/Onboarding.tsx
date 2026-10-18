import { useState } from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { useShell } from "@/components/AppShell"
import { firstOpen, KEY, markDone, markSkipped, readProgress, STEPS, stateOf, writeProgress, type Progress } from "@/lib/onboarding"
import { BODIES, CHECKS } from "@/screens/OnboardingSteps"

const MARK = { done: "Done", skipped: "Skipped", todo: "To do" } as const

/** Guided setup: a checklist and one step at a time. Each step says why, checks before moving on, and can be skipped. */
export function Onboarding() {
  const { lsKey } = useShell()
  const key = lsKey(KEY)
  const [progress, setProgress] = useState<Progress>(() => readProgress(key))
  const [index, setIndex] = useState(() => firstOpen(progress))
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState("")

  const step = STEPS[index]
  const Body = BODIES[step.id]
  const last = index === STEPS.length - 1
  const update = (p: Progress) => {
    setProgress(p)
    writeProgress(key, p)
  }
  const go = (i: number) => {
    setProblem("")
    setIndex(Math.min(Math.max(i, 0), STEPS.length - 1))
  }
  const next = () => go(index + 1)

  const proceed = async () => {
    setBusy(true)
    setProblem("")
    try {
      const msg = await CHECKS[step.id]?.()
      if (msg) return setProblem(msg)
      update(markDone(progress, step.id))
      if (!last) next()
    } catch (e) {
      setProblem(`Couldn’t check that: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setBusy(false)
    }
  }
  const skip = () => {
    update(markSkipped(progress, step.id))
    if (!last) next()
  }

  const doneCount = STEPS.filter((s) => stateOf(progress, s.id) !== "todo").length
  return (
    <div className="grid gap-4 md:grid-cols-[16rem_1fr]" aria-label="Guided setup">
      <Card>
        <CardContent className="space-y-3 p-4">
          <h2 className="text-sm font-semibold">Guided setup</h2>
          <p className="text-xs text-muted-foreground">{doneCount} of {STEPS.length} steps finished or skipped</p>
          <ol className="space-y-1">
            {STEPS.map((s, i) => (
              <li key={s.id}>
                <Button
                  size="sm"
                  variant={i === index ? "default" : "ghost"}
                  className="h-auto w-full justify-between whitespace-normal text-left"
                  aria-current={i === index ? "step" : undefined}
                  onClick={() => go(i)}
                >
                  <span>{i + 1}. {s.title}</span>
                  <span className="text-xs opacity-80">{MARK[stateOf(progress, s.id)]}</span>
                </Button>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>

      <div className="space-y-4">
        {progress.finished && (
          <p role="status" className="rounded-lg bg-muted p-3 text-sm">
            You have been through every step. You can open any of them again from the list. <a className="underline" href="#/home">Go to Home</a>.
          </p>
        )}
        <Card>
          <CardContent className="space-y-3 p-4">
            <h2 className="text-base font-semibold">{step.title}</h2>
            <p className="text-sm text-muted-foreground">{step.why}</p>
            <Body />
            {problem && <p role="alert" className="text-sm">{problem}</p>}
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="ghost" disabled={index === 0 || busy} onClick={() => go(index - 1)}>
                Back
              </Button>
              <Button size="sm" disabled={busy} onClick={proceed}>
                {busy ? "Checking…" : last ? "Finish" : "Continue"}
              </Button>
              <Button size="sm" variant="outline" disabled={busy} onClick={skip}>
                {step.optional ? "Skip this step" : "Skip for now"}
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
