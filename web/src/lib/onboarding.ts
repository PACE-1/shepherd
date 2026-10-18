import type { IcuConnection, LlmConnection, PlanRead, SettingsRead, WeatherLocation } from "@/api/types"
import type { RiderForm } from "@/lib/settings"

// Guided onboarding: the steps, the progress the browser remembers, and the checks that gate "Continue".

export interface StepInfo {
  id: string
  title: string
  /** Why the step matters, shown to the rider. */
  why: string
  /** An optional step can be skipped without losing anything the app needs. */
  optional: boolean
}

export const STEPS: StepInfo[] = [
  {
    id: "icu",
    title: "Connect intervals.icu",
    why: "intervals.icu is where your rides, sleep and heart-rate data come from. Without it Shepherd cannot tell how tired you are or whether the plan is working.",
    optional: false,
  },
  {
    id: "rider",
    title: "Your rider numbers",
    why: "Your FTP, weight and heart rates set every target and training zone. Wrong numbers mean sessions that are too easy or too hard.",
    optional: false,
  },
  {
    id: "ai",
    title: "AI coach (optional)",
    why: "An AI provider lets you ask the coach questions about your training. Everything else works without one.",
    optional: true,
  },
  {
    id: "folders",
    title: "Workout folders",
    why: "Shepherd has a built-in workout library. Add a folder if you have your own .zwo workout files.",
    optional: true,
  },
  {
    id: "location",
    title: "Where do you ride?",
    why: "For the weather forecast next to your outdoor sessions, so a stormy day can be swapped for an indoor one. Optional: without a location the forecast simply stays off.",
    optional: true,
  },
  {
    id: "goal",
    title: "Goal and weekly availability",
    why: "The plan is built around your goal and the hours you can ride. Tell it when you are free and it will not schedule rides you cannot do.",
    optional: false,
  },
  {
    id: "tour",
    title: "A short tour",
    why: "A quick look at where everything lives, so you know where to go next.",
    optional: true,
  },
]

export const TOUR = [
  { name: "Home", href: "#/home", text: "Your day at a glance: how ready you are, what to ride today and how your week is going." },
  { name: "Training Plan", href: "#/plan", text: "Your plan week by week. Move, swap or skip a session, add a race, or record time off." },
  { name: "Workout Library", href: "#/library", text: "Every workout, with filters. Download one to ride on your head unit or trainer app." },
  { name: "Analysis", href: "#/analysis", text: "Your rides and how your fitness is changing over time." },
  { name: "Settings", href: "#/settings", text: "Your rider numbers, connections, folders and appearance. You can run this guided setup again from here." },
] as const

export interface Progress {
  done: string[]
  skipped: string[]
  finished: boolean
}
export const EMPTY: Progress = { done: [], skipped: [], finished: false }

export const KEY = "shepherd_onboarding"

// Browser storage can be blocked or empty (private windows): progress then simply starts over.
export function readProgress(key: string): Progress {
  try {
    const o = JSON.parse(localStorage.getItem(key) || "null")
    const ids = (x: unknown) => (Array.isArray(x) ? x.filter((v): v is string => typeof v === "string") : [])
    return o ? { done: ids(o.done), skipped: ids(o.skipped), finished: o.finished === true } : EMPTY
  } catch {
    return EMPTY
  }
}
export function writeProgress(key: string, p: Progress) {
  try {
    localStorage.setItem(key, JSON.stringify(p))
  } catch {
    /* not saved; the walk-through still works for this visit */
  }
}

const without = (xs: string[], id: string) => xs.filter((x) => x !== id)
export const markDone = (p: Progress, id: string): Progress => {
  const done = [...without(p.done, id), id]
  return { done, skipped: without(p.skipped, id), finished: STEPS.every((s) => done.includes(s.id) || p.skipped.includes(s.id)) }
}
export const markSkipped = (p: Progress, id: string): Progress => {
  const skipped = [...without(p.skipped, id), id]
  return { done: without(p.done, id), skipped, finished: STEPS.every((s) => skipped.includes(s.id) || p.done.includes(s.id)) }
}
export const stateOf = (p: Progress, id: string): "done" | "skipped" | "todo" =>
  p.done.includes(id) ? "done" : p.skipped.includes(id) ? "skipped" : "todo"

/** Index of the first step not yet done or skipped; the last step when everything is. */
export const firstOpen = (p: Progress) => {
  const i = STEPS.findIndex((s) => stateOf(p, s.id) === "todo")
  return i < 0 ? STEPS.length - 1 : i
}

// ── Checks: a message when the step is not complete, null when it is ────────

export const icuCheck = (c: IcuConnection) => (c.connected ? null : "intervals.icu is not connected yet. Connect it, or skip this step.")
export const riderCheck = (s: SettingsRead) =>
  s.lthr_is_set ? null : "Save your rider numbers first (heart-rate threshold included), or skip this step."
export const aiCheck = (c: LlmConnection) => (c.configured ? null : "No AI provider is connected yet. Connect one, or skip this step.")
export const locationCheck = (l: WeatherLocation) => (l.has_location ? null : "No place picked yet. Search for one, or skip this step.")
export const goalCheck =(p: PlanRead) => (p.plan_json?.weeks?.length ? null : "Create a training plan first, or skip this step.")

/** Every number is sent, not only the changed ones: saving is the rider confirming them. */
export const riderPayload = (f: RiderForm): Record<string, number | string> => ({
  weight: Number(f.weight),
  ftp: Number(f.ftp),
  lthr: Number(f.lthr),
  max_hr: Number(f.maxHr),
  target_mode: f.targetMode,
})
