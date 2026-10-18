import { useSyncExternalStore } from "react"

import { AppShell, isTab } from "@/components/AppShell"
import { Analysis } from "@/screens/Analysis"
import { Dfa } from "@/screens/Dfa"
import { Home } from "@/screens/Home"
import { Injury } from "@/screens/Injury"
import { Library } from "@/screens/Library"
import { Onboarding } from "@/screens/Onboarding"
import { Plan } from "@/screens/Plan"
import { ProfilePicker } from "@/screens/ProfilePicker"
import { ProfileSetup } from "@/screens/ProfileSetup"
import { RideDetail } from "@/screens/RideDetail"
import { Setup } from "@/screens/Setup"
import { Settings } from "@/screens/Settings"
import { Shuffle } from "@/screens/Shuffle"
import { WorkoutBuilder } from "@/screens/WorkoutBuilder"

// ponytail: hash routing, no router dependency. Swap for react-router when nested routes or loaders are needed.
const subscribe = (cb: () => void) => {
  window.addEventListener("hashchange", cb)
  return () => window.removeEventListener("hashchange", cb)
}
// The intervals.icu OAuth callback returns to /v2/?wizard=...&icu=..., with no hash.
const currentRoute = () =>
  window.location.hash.replace(/^#\/?/, "") || (new URLSearchParams(window.location.search).get("wizard") ?? "")
const useRoute = () => useSyncExternalStore(subscribe, currentRoute)

export function App() {
  const route = useRoute()
  if (route === "profile-picker") return <ProfilePicker />
  if (route === "profile-setup") return <ProfileSetup />
  if (route === "setup") return <Setup />
  const [head, ...rest] = route.split("/")
  if (head === "ride" && rest.length)
    return (
      <AppShell tab="analysis">
        <RideDetail id={decodeURIComponent(rest.join("/"))} />
      </AppShell>
    )
  if (route === "onboarding") return <AppShell tab="home"><Onboarding /></AppShell>
  if (head === "builder")
    return (
      <AppShell tab="library">
        <WorkoutBuilder file={rest.length ? decodeURIComponent(rest.join("/")) : undefined} />
      </AppShell>
    )
  if (head === "injury") return <AppShell tab="plan"><Injury /></AppShell>
  const tab = isTab(route) ? route : "home"
  return (
    <AppShell tab={tab}>
      {tab === "dfa" ? <Dfa /> : tab === "home" ? <Home /> : tab === "plan" ? <Plan /> : tab === "library" ? <Library /> : tab === "picker" ? <Shuffle /> : tab === "analysis" ? <Analysis /> : <Settings />}
    </AppShell>
  )
}

export default App
