import { cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { badge, validTime } from "@/lib/notifications"
import { NotificationsSettings } from "@/screens/Notifications"
import { NotificationsBell } from "@/screens/NotificationsBell"

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })
const SETTINGS = { has_url: false, events: { readiness: true, missed: true, sync_failure: true, gear_due: true }, readiness_time: "" }
const ITEM = { id: 1, event: "missed", day: "2026-10-17", title: "Shepherd: missed session", body: "Yesterday's z2 has no activity.", ts: "2026-10-18T07:00:00", read: false }

function mock(routes: Record<string, (body: unknown, method?: string) => Response>) {
  const calls: { url: string; method?: string; body: unknown }[] = []
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const body = init?.body ? JSON.parse(init.body as string) : undefined
    calls.push({ url, method: init?.method, body })
    return (routes[url] ?? (() => json({}, 404)))(body, init?.method)
  }))
  return calls
}
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe("helpers", () => {
  it("accepts HH:MM or empty, and caps the badge", () => {
    expect(["", "07:30", "23:59"].every(validTime)).toBe(true)
    expect(["7:30", "24:00", "07:60", "noon"].some(validTime)).toBe(false)
    expect([badge(0), badge(3), badge(12)]).toEqual(["", "3", "9+"])
  })
})

describe("Notifications settings", () => {
  it("saves a toggle on its own, and never shows or returns the address", async () => {
    let s = SETTINGS
    const calls = mock({
      "/api/notifications/settings": (b, m) => (m === "PUT" ? ((s = { ...s, ...(b as object), has_url: true } as typeof SETTINGS), json(s)) : json(s)),
    })
    render(<NotificationsSettings />)
    await userEvent.click(await screen.findByRole("checkbox", { name: /Missed session/ }))
    await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ events: { missed: false } }))
    await userEvent.type(screen.getByLabelText(/ntfy address/), "https://ntfy.example.com/secret-topic")
    await userEvent.click(screen.getByRole("button", { name: "Save address" }))
    expect(await screen.findByText("Address saved.")).toBeTruthy()
    expect(calls.filter((c) => c.method === "PUT").at(-1)?.body).toEqual({ ntfy_url: "https://ntfy.example.com/secret-topic" })
    expect((screen.getByLabelText(/ntfy address/) as HTMLInputElement).value).toBe("")
    expect(document.body.innerHTML).not.toContain("secret-topic")
    expect(screen.getByRole("button", { name: "Send a test" }).hasAttribute("disabled")).toBe(false)
  })

  it("blocks a bad time, and shows the server's refusal of a bad address", async () => {
    mock({
      "/api/notifications/settings": (_b, m) => (m === "PUT" ? json({ error: "The address must start with http:// or https:// and name a host." }, 400) : json(SETTINGS)),
    })
    render(<NotificationsSettings />)
    await userEvent.type(await screen.findByLabelText(/Send readiness at/), "9am")
    expect(screen.getByRole("alert").textContent).toContain("HH:MM")
    expect(screen.getByRole("button", { name: "Set time" }).hasAttribute("disabled")).toBe(true)
    await userEvent.type(screen.getByLabelText(/ntfy address/), "ftp://x")
    await userEvent.click(screen.getByRole("button", { name: "Save address" }))
    expect(await screen.findByText(/must start with http/)).toBeTruthy()
  })

  it("reports a failed test send", async () => {
    mock({
      "/api/notifications/settings": () => json({ ...SETTINGS, has_url: true }),
      "/api/notifications/test": () => json({ ok: false, error: "The server answered 403." }),
    })
    render(<NotificationsSettings />)
    await userEvent.click(await screen.findByRole("button", { name: "Send a test" }))
    expect(await screen.findByText(/The server answered 403/)).toBeTruthy()
  })
})

describe("Notifications bell", () => {
  it("shows the unread count, lists the notices, and marks them read", async () => {
    let list = { items: [ITEM], unread: 1 }
    const calls = mock({
      "/api/notifications": () => json(list),
      "/api/notifications/read": () => ((list = { items: [{ ...ITEM, read: true }], unread: 0 }), json(list)),
    })
    render(<NotificationsBell />)
    const bell = await screen.findByRole("button", { name: "Notifications, 1 unread" })
    await userEvent.click(bell)
    expect(screen.getByText("Yesterday's z2 has no activity.")).toBeTruthy()
    await userEvent.click(screen.getByRole("button", { name: "Mark all read" }))
    expect(await screen.findByRole("button", { name: "Notifications" })).toBeTruthy()
    expect(calls.some((c) => c.url === "/api/notifications/read" && c.method === "POST")).toBe(true)
  })

  it("stays quiet and empty when the server cannot be reached", async () => {
    mock({ "/api/notifications": () => json({}, 500) })
    render(<NotificationsBell />)
    await userEvent.click(await screen.findByRole("button", { name: "Notifications" }))
    expect(screen.getByText(/Nothing yet/)).toBeTruthy()
  })
})
