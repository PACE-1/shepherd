import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react"

import { CalendarDaysIcon, ChartLineIcon, EllipsisIcon, HomeIcon, LibraryIcon, SettingsIcon, type LucideIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Logo } from "@/components/Logo"
import { ThemeToggle } from "@/components/ThemeToggle"
import { api } from "@/lib/api"
import { Notices } from "@/screens/Notices"
import { NotificationsBell } from "@/screens/NotificationsBell"

export const TABS = [
  { id: "home", label: "Home" },
  { id: "picker", label: "Workout Shuffle" },
  { id: "library", label: "Workout Library" },
  { id: "plan", label: "Training Plan" },
  { id: "analysis", label: "Analysis" },
  { id: "dfa", label: "DFA α1" },
  { id: "settings", label: "Settings" },
] as const
export type TabId = (typeof TABS)[number]["id"]
export const isTab = (r: string): r is TabId => TABS.some((t) => t.id === r)

// Phone layout: five tabs on a bottom bar under the thumb, the rest behind "More".
const BAR: Partial<Record<TabId, { short: string; Icon: LucideIcon }>> = {
  home: { short: "Home", Icon: HomeIcon },
  plan: { short: "Plan", Icon: CalendarDaysIcon },
  library: { short: "Library", Icon: LibraryIcon },
  analysis: { short: "Analysis", Icon: ChartLineIcon },
  settings: { short: "Settings", Icon: SettingsIcon },
}
const barTab = "max-md:h-14 max-md:min-w-0 max-md:flex-1 max-md:flex-col max-md:gap-0.5 max-md:rounded-none max-md:px-0 max-md:text-[11px]"

interface Shell {
  activeId: string
  // Same per-profile localStorage key shape as the legacy dashboard: "<base>:<profile id>".
  lsKey: (base: string) => string
}
const ShellContext = createContext<Shell>({ activeId: "", lsKey: (b) => `${b}:` })
export const useShell = () => useContext(ShellContext)

export function AppShell({ tab, children }: { tab: TabId; children: ReactNode }) {
  const [activeId, setActiveId] = useState<string | null>(null)

  useEffect(() => {
    api<{ active: string }>("/api/profiles")
      .then((d) => setActiveId(d.active ?? ""))
      .catch(() => setActiveId(""))
  }, [])

  const [more, setMore] = useState(false)
  useEffect(() => {
    if (!more) return
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setMore(false)
    window.addEventListener("keydown", esc)
    return () => window.removeEventListener("keydown", esc)
  }, [more])

  const value = useMemo(() => ({ activeId: activeId ?? "", lsKey: (b: string) => `${b}:${activeId}` }), [activeId])
  if (activeId === null) return null
  const overflowActive = !BAR[tab]
  return (
    <ShellContext.Provider value={value}>
      <div className="mx-auto max-w-7xl px-4 py-4 max-md:pb-[calc(5.5rem+env(safe-area-inset-bottom))]">
        <div className="mb-3 flex items-center gap-1.5 text-base font-semibold tracking-tight md:hidden">
          <Logo />
          Shepherd
        </div>
        <nav
          className="flex flex-wrap items-center gap-1 border-b pb-3 md:mb-6 max-md:fixed max-md:inset-x-0 max-md:bottom-0 max-md:z-40 max-md:flex-nowrap max-md:gap-0 max-md:border-t max-md:border-b-0 max-md:bg-background max-md:px-1 max-md:pt-1 max-md:pb-[env(safe-area-inset-bottom)]"
          aria-label="Sections"
        >
          <a href="#/home" className="mr-3 flex items-center gap-1.5 text-base font-semibold tracking-tight max-md:hidden">
            <Logo />
            Shepherd
          </a>
          {TABS.map((t) => {
            const bar = BAR[t.id]
            return (
              <Button
                key={t.id}
                size="sm"
                variant={t.id === tab ? "default" : "ghost"}
                aria-current={t.id === tab ? "page" : undefined}
                aria-label={t.label}
                className={bar ? barTab : "max-md:hidden"}
                render={<a href={`#/${t.id}`} />}
              >
                {bar && <bar.Icon className="size-5 md:hidden" aria-hidden />}
                <span className="max-md:hidden">{t.label}</span>
                {bar && (
                  <span className="md:hidden" aria-hidden>
                    {bar.short}
                  </span>
                )}
              </Button>
            )
          })}
          <span className="flex-1 max-md:hidden" />
          <Button size="sm" variant="ghost" className="max-md:hidden" render={<a href="#/profile-picker" />}>
            Switch rider
          </Button>
          <span className="max-md:hidden">
            <NotificationsBell />
            <ThemeToggle />
          </span>
          <Button
            size="sm"
            variant={overflowActive ? "default" : "ghost"}
            className={`${barTab} md:hidden`}
            aria-expanded={more}
            aria-controls="more-menu"
            onClick={() => setMore((m) => !m)}
          >
            <EllipsisIcon className="size-5" aria-hidden />
            More
          </Button>
          {more && (
            <div
              id="more-menu"
              className="absolute right-2 bottom-full mb-2 flex w-60 flex-col gap-1 rounded-xl border bg-popover p-2 text-popover-foreground shadow-lg md:hidden"
              onClick={(e) => (e.target as HTMLElement).closest("a") && setMore(false)}
            >
              {TABS.filter((t) => !BAR[t.id]).map((t) => (
                <Button
                  key={t.id}
                  variant={t.id === tab ? "default" : "ghost"}
                  className="h-11 justify-start"
                  aria-current={t.id === tab ? "page" : undefined}
                  render={<a href={`#/${t.id}`} />}
                >
                  {t.label}
                </Button>
              ))}
              <Button variant="ghost" className="h-11 justify-start" render={<a href="#/profile-picker" />}>
                Switch rider
              </Button>
              <div className="flex items-center justify-between px-3 text-sm">
                Notifications
                <NotificationsBell />
              </div>
              <div className="flex items-center justify-between px-3 text-sm">
                Theme
                <ThemeToggle />
              </div>
            </div>
          )}
        </nav>
        <Notices />
        {children}
      </div>
    </ShellContext.Provider>
  )
}
