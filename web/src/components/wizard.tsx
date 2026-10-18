import type { IcuConnection } from "@/lib/setup"

// Shared by both setup wizards (first-run and new-profile).

export function StepDots({ step, total }: { step: number; total: number }) {
  return (
    <div className="mb-6 flex justify-center gap-2" aria-label={`Step ${step} of ${total}`}>
      {Array.from({ length: total }, (_, i) => (
        <span key={i} className={`h-2 w-8 rounded-full ${i < step ? "bg-primary" : "bg-muted"}`} />
      ))}
    </div>
  )
}

const COMPARISON: [string, string, string, boolean][] = [
  ["Your rides", "Arrive by themselves from the apps and devices you connect to it", "You import each ride's FIT file", false],
  ["Fitness & form", "Fitness, fatigue and form updated every day", "Computed from the rides you import", false],
  ["Readiness", "HRV and sleep from your watch, every morning", "HRV typed in by hand", false],
  ["Workouts", "Pushed to your device via the intervals.icu calendar", "Download each one as ZWO or FIT", false],
  ["Your plan", "The full plan, adapting to what you ride", "The full plan, adapting to what you import", true],
  ["Account", "Free account; connect your bike computer, watch or training app to it once", "Nothing to sign up for", true],
]

export function IcuComparison() {
  return (
    <>
      <div className="grid grid-cols-[auto_1fr_1fr] gap-x-3 gap-y-2 text-left text-sm">
        <span />
        <span className="font-semibold">
          With intervals.icu <em className="text-xs font-normal">Recommended</em>
        </span>
        <span className="font-semibold">Without</span>
        {COMPARISON.map(([label, withIcu, without, automatic]) => (
          <div key={label} className="contents">
            <span className="text-muted-foreground">{label}</span>
            <span>✓ {withIcu}</span>
            <span>
              {automatic ? "✓" : "✎"} {without}
            </span>
          </div>
        ))}
      </div>
      <p className="text-xs text-muted-foreground">
        How linking works: 1 Sign in on intervals.icu in your browser · 2 Approve once · 3 You are back
        here, linked. You can always connect later in Settings.
      </p>
    </>
  )
}

export function LinkedCard({ connection, next }: { connection: IcuConnection | null; next: string }) {
  return (
    <div className="rounded-lg border p-3 text-left">
      <div className="font-semibold">✓ Connected to intervals.icu</div>
      <div>{connection?.name || "Your account"}</div>
      {connection?.athlete_id && (
        <div className="text-xs text-muted-foreground">athlete {connection.athlete_id}</div>
      )}
      <div className="text-xs text-muted-foreground">{next}</div>
    </div>
  )
}
