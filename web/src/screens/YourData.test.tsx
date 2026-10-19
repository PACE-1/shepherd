import { cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, expect, it, vi } from "vitest"

import { YourData } from "@/screens/YourData"

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })
function mock(routes: Record<string, (init?: RequestInit) => Response>) {
  const calls: { method?: string; body: unknown }[] = []
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ method: init?.method, body: init?.body })
    return (routes[`${init?.method ?? "GET"} ${url}`] ?? (() => json({}, 404)))(init)
  }))
  return calls
}
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

const staged = { pending: true, files: 12, data_format: 1, app_version: "4.0.0", created_at: "2026-10-01T07:00:00Z", secrets_excluded: true }

it("links each export and says the backup has no keys", () => {
  mock({ "GET /api/import/backup": () => json({ pending: false }) })
  render(<YourData />)
  expect(screen.getByRole("link", { name: "Activities (CSV)" }).getAttribute("href")).toBe("/api/export/activities.csv")
  expect(screen.getByRole("link", { name: "Full backup (.tar.gz)" }).getAttribute("href")).toBe("/api/export/backup")
  expect(screen.getByText(/leaves out your intervals.icu and AI keys/)).toBeTruthy()
})

it("stages a backup, offers to cancel it, and shows the server's refusal", async () => {
  let waiting = false
  let refusal: Response | null = null
  const calls = mock({
    "GET /api/import/backup": () => json(waiting ? staged : { pending: false }),
    "POST /api/import/backup": () => { if (refusal) return refusal; waiting = true; return json(staged) },
    "DELETE /api/import/backup": () => { waiting = false; return json({ pending: false }) },
  })
  render(<YourData />)
  const input = document.querySelector('input[type="file"]') as HTMLInputElement
  await userEvent.upload(input, new File(["x"], "b.tar.gz"))
  await userEvent.click(screen.getByRole("button", { name: "Check and stage" }))
  expect((await screen.findByRole("status")).textContent).toContain("12 files")
  expect((calls.find((c) => c.method === "POST")!.body as FormData).get("file")).toBeTruthy()
  await userEvent.click(screen.getByRole("button", { name: "Cancel restore" }))
  await waitFor(() => expect(screen.queryByRole("status")).toBeNull())
  refusal = json({ detail: "That file is not a usable Shepherd backup: checksum mismatch" }, 400)
  await userEvent.upload(input, new File(["y"], "bad.tar.gz"))
  await userEvent.click(screen.getByRole("button", { name: "Check and stage" }))
  expect((await screen.findByRole("alert")).textContent).toContain("checksum mismatch")
})
