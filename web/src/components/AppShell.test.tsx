import { cleanup, render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { AppShell, TABS } from "@/components/AppShell"
import { ThemeProvider } from "@/components/theme-provider"

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => new Response(JSON.stringify(url === "/api/profiles" ? { active: "default", profiles: [] } : {}))),
  )
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const shell = (tab: (typeof TABS)[number]["id"] = "home") =>
  render(
    <ThemeProvider>
      <AppShell tab={tab}>
        <p>content</p>
      </AppShell>
    </ThemeProvider>,
  )

describe("AppShell navigation", () => {
  it("lists every section once, marks the current one, and keeps the route order", async () => {
    shell("plan")
    const nav = await screen.findByRole("navigation", { name: "Sections" })
    const links = within(nav).getAllByRole("link")
    for (const t of TABS) expect(within(nav).getByRole("link", { name: t.label })).toBeTruthy()
    expect(within(nav).getByRole("link", { name: "Training Plan" }).getAttribute("aria-current")).toBe("page")
    expect(links.filter((l) => l.getAttribute("aria-current") === "page")).toHaveLength(1)
  })

  it("keeps the less-used sections behind More, which opens, navigates and closes", async () => {
    shell("home")
    const nav = await screen.findByRole("navigation", { name: "Sections" })
    const more = within(nav).getByRole("button", { name: "More" })
    expect(more.getAttribute("aria-expanded")).toBe("false")
    expect(document.getElementById("more-menu")).toBeNull()
    await userEvent.click(more)
    expect(more.getAttribute("aria-expanded")).toBe("true")
    const menu = document.getElementById("more-menu")!
    for (const name of ["Workout Shuffle", "DFA α1", "Switch rider"]) expect(within(menu).getByRole("link", { name })).toBeTruthy()
    expect(within(menu).getByRole("button", { name: /theme/i })).toBeTruthy()
    await userEvent.click(within(menu).getByRole("link", { name: "DFA α1" }))
    expect(document.getElementById("more-menu")).toBeNull()
  })

  it("closes More with Escape", async () => {
    shell("home")
    await userEvent.click(await screen.findByRole("button", { name: "More" }))
    expect(document.getElementById("more-menu")).not.toBeNull()
    await userEvent.keyboard("{Escape}")
    expect(document.getElementById("more-menu")).toBeNull()
  })

  it("highlights More when the current section lives behind it", async () => {
    shell("dfa")
    const more = await screen.findByRole("button", { name: "More" })
    expect(more.className).toContain("bg-primary")
  })
})
