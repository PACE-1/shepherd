import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react"

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

  const value = useMemo(() => ({ activeId: activeId ?? "", lsKey: (b: string) => `${b}:${activeId}` }), [activeId])
  if (activeId === null) return null
  return (
    <ShellContext.Provider value={value}>
      <div className="mx-auto max-w-7xl px-4 py-4">
        <nav className="mb-6 flex flex-wrap items-center gap-1 border-b pb-3" aria-label="Sections">
          <a href="#/home" className="mr-3 flex items-center gap-1.5 text-base font-semibold tracking-tight">
            <Logo />
            Shepherd
          </a>
          {TABS.map((t) => (
            <Button
              key={t.id}
              size="sm"
              variant={t.id === tab ? "default" : "ghost"}
              aria-current={t.id === tab ? "page" : undefined}
              render={<a href={`#/${t.id}`} />}
            >
              {t.label}
            </Button>
          ))}
          <span className="flex-1" />
          <Button size="sm" variant="ghost" render={<a href="#/profile-picker" />}>
            Switch rider
          </Button>
          <NotificationsBell />
          <ThemeToggle />
        </nav>
        <Notices />
        {children}
      </div>
    </ShellContext.Provider>
  )
}
