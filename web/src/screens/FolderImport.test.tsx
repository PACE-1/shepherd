import { cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { IcuComparison } from "@/components/wizard"
import { scanSummary } from "@/lib/folderImport"
import { FolderImport } from "@/screens/FolderImport"

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })
const EMPTY = { folder: "", recursive: false, running: false, max_files: 200, last_scan: null }
const SCAN = {
  started_at: "2026-10-18T09:00:00", finished_at: "2026-10-18T09:00:05", imported: 3, duplicate: 2, failed: 1,
  already_imported: 0, remaining: 0, aborted: false, error: "", failures: [{ file: "broken.fit", reason: "could not read this FIT file" }],
}

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

describe("scanSummary", () => {
  it("says what came in, what was skipped and what failed", () => {
    expect(scanSummary(SCAN)).toBe("3 rides imported, 2 already in Shepherd, 1 failed.")
    expect(scanSummary({ ...SCAN, imported: 1, remaining: 40 })).toBe("1 ride imported, 2 already in Shepherd, 1 failed, 40 left for the next scan.")
    expect(scanSummary({ ...SCAN, error: "No folder is set." })).toBe("No folder is set.")
  })
})

describe("Folder import", () => {
  it("explains the Docker volume rule and shows the server's refusal", async () => {
    mock({ "/api/folder-import": (_b, m) => (m === "PUT" ? json({ detail: "That folder does not exist on the machine Shepherd runs on. In Docker, it must be a path inside a mounted volume." }, 400) : json(EMPTY)) })
    render(<FolderImport />)
    expect(await screen.findByText(/must be a folder inside a\s+mounted volume/)).toBeTruthy()
    expect(screen.queryByRole("button", { name: "Scan now" })).toBeNull()
    await userEvent.type(screen.getByLabelText("Folder with your .fit files"), "/nope")
    await userEvent.click(screen.getByRole("button", { name: "Set folder" }))
    expect((await screen.findByRole("alert")).textContent).toMatch(/does not exist/)
    expect((screen.getByLabelText("Folder with your .fit files") as HTMLInputElement).value).toBe("/nope")
  })

  it("sets a folder, scans, polls until done and shows the counts", async () => {
    let state: Record<string, unknown> = { ...EMPTY }
    let polls = 0
    const calls = mock({
      "/api/folder-import": (b, m) => {
        if (m === "PUT") return json((state = { ...state, ...(b as object) }))
        if (state.running && ++polls >= 2) state = { ...state, running: false, last_scan: SCAN }
        return json(state)
      },
      "/api/folder-import/scan": () => ((state = { ...state, running: true }), json({ started: true, running: true })),
    })
    render(<FolderImport />)
    await userEvent.type(await screen.findByLabelText("Folder with your .fit files"), "/data/rides")
    await userEvent.click(screen.getByRole("button", { name: "Set folder" }))
    expect(await screen.findByText("/data/rides")).toBeTruthy()
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ folder: "/data/rides" })

    await userEvent.click(screen.getByRole("checkbox", { name: /Include subfolders/ }))
    await waitFor(() => expect(calls.filter((c) => c.method === "PUT").at(-1)?.body).toEqual({ recursive: true }))

    await userEvent.click(screen.getByRole("button", { name: "Scan now" }))
    expect(await screen.findByRole("button", { name: "Scanning…" })).toBeTruthy()
    expect(await screen.findByText(/3 rides imported, 2 already in Shepherd, 1 failed/, {}, { timeout: 4000 })).toBeTruthy()
    expect(screen.getByText("broken.fit")).toBeTruthy()
  })
})

describe("setup copy (#31)", () => {
  it("does not single out one device maker as the way to get rides in", () => {
    render(<IcuComparison />)
    expect(screen.getByText(/connect your bike computer, watch or training app to it once/)).toBeTruthy()
    expect(document.body.textContent).not.toMatch(/Garmin|Strava/)
  })
})
