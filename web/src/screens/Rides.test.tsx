import { cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { Records } from "@/screens/Records"
import { RideDetail } from "@/screens/RideDetail"
import { RideTools } from "@/screens/RideTools"

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })
type Handler = (body: unknown, init?: RequestInit) => Response
function mock(routes: Record<string, Handler>) {
  const calls: { url: string; method?: string; body: unknown; init?: RequestInit }[] = []
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const raw = init?.body
    const body = typeof raw === "string" ? JSON.parse(raw) : raw
    calls.push({ url, method: init?.method, body, init })
    const key = Object.keys(routes).find((k) => url.startsWith(k))
    return key ? routes[key](body, init) : json({}, 404)
  }))
  return calls
}
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

const RIDE = {
  ride_id: "icu_9", name: "Sunday long", started_at: "2026-10-11T08:00:00", duration_s: 7200, distance_km: 61.234, elevation_m: 640, avg_power_w: 190, np_w: 205, if_pct: 82, tss: 101, kj: 1400, avg_hr: 142, hr_max: 171, avg_cadence: 88, decoupling_pct: 3.4, rpe: 6,
  time_in_zone: { z1: 600, z2: 4800, z3: 1200, z4: 600, z5: 0, z6: 0, z7: 0 },
  intervals: [{ name: "Climb", duration_s: 600, avg_power_w: 260, ftp_pct: 104 }],
  prs: [{ duration_s: 1200, watts: 280, tier: "major" }],
  samples: { t_s: [0, 60, 120], power_w: [100, 200, 150], hr_bpm: [120, 140, 150], elevation_m: [0, 0, 0] },
}

describe("RideTools", () => {
  const pick = async (name = "ride.fit") => {
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    await userEvent.upload(input, new File(["x"], name))
  }

  it("uploads the file as fit_file and links to the new ride", async () => {
    const calls = mock({ "/api/ride/import": () => json({ ride_id: "2026-10-16T08-00-00", icu_upload: { ok: true } }) })
    const changed = vi.fn()
    render(<RideTools onChanged={changed} />)
    expect((screen.getByRole("button", { name: "Import ride" }) as HTMLButtonElement).disabled).toBe(true)
    await pick()
    await userEvent.click(screen.getByRole("button", { name: "Import ride" }))
    expect((await screen.findByRole("status")).textContent).toContain("Sent to intervals.icu.")
    expect((calls[0].body as FormData).get("fit_file")).toBeTruthy()
    expect(screen.getByRole("link", { name: "Open it" }).getAttribute("href")).toBe("#/ride/fit_2026-10-16T08-00-00")
    expect(changed).toHaveBeenCalled()
  })

  it("shows the server's reason when the file is refused", async () => {
    mock({ "/api/ride/import": () => json({ detail: "could not read this FIT file: bad header" }, 422) })
    render(<RideTools onChanged={() => {}} />)
    await pick()
    await userEvent.click(screen.getByRole("button", { name: "Import ride" }))
    expect((await screen.findByRole("alert")).textContent).toContain("bad header")
  })

  it("syncs and reports the count, or says intervals.icu is not connected", async () => {
    let body: unknown = { added: 2, total: 40 }
    mock({ "/api/rides/sync": () => json(body) })
    render(<RideTools onChanged={() => {}} />)
    await userEvent.click(screen.getByRole("button", { name: "Sync from intervals.icu" }))
    expect((await screen.findByRole("status")).textContent).toContain("2 new rides from intervals.icu (40 stored)")
    body = { added: 0, total: 0, skipped: "no_credentials" }
    await userEvent.click(screen.getByRole("button", { name: "Sync from intervals.icu" }))
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("not connected"))
  })
})

describe("RideDetail", () => {
  const routes = (over: Record<string, Handler> = {}) => ({
    "/api/ride/icu_9/detail": () => json(RIDE),
    "/api/ride/icu_9/ftp-test-analysis": () => json({ error: "no FTP-test suggestion on this ride" }, 404),
    ...over,
  })

  it("shows the ride's numbers, zones, intervals, records and charts", async () => {
    mock(routes())
    render(<RideDetail id="icu_9" />)
    expect(await screen.findByText("61.2 km")).toBeTruthy()
    expect(screen.getByText("205 W")).toBeTruthy()
    expect(screen.getByText("142 / 171")).toBeTruthy()
    expect(screen.getByText("Z2 Endurance")).toBeTruthy()
    expect(screen.getByText("Climb")).toBeTruthy()
    expect(screen.getByText(/20 min: 280 W \(major\)/)).toBeTruthy()
    expect(screen.getByRole("img", { name: "Power over the ride" })).toBeTruthy()
    expect(screen.getByRole("link", { name: "Download .fit" }).getAttribute("href")).toBe("/api/rides/icu_9/fit")
    expect(screen.queryByRole("button", { name: "Delete ride…" })).toBeNull()
    expect(screen.queryByText("FTP test")).toBeNull()
  })

  it("shows pace and heart-rate zones for a run, with no power rows", async () => {
    mock(routes({
      "/api/ride/icu_9/detail": () => json({ ride_id: "icu_9", name: "Tempo run", sport: "Run", started_at: "2026-10-11T08:00:00", duration_s: 3000, moving_s: 3000, distance_km: 10, elevation_m: 80, avg_hr: 160, hr_max: 175, tss: 70, avg_power_w: null,
        time_in_zone: { z1: 0, z2: 0, z3: 0, z4: 0, z5: 0, z6: 0, z7: 0 }, hr_time_in_zone: { z1: 300, z2: 1200, z3: 1500, z4: 0, z5: 0, z6: 0, z7: 0 },
        samples: { t_s: [0, 60, 120], power_w: [0, 0, 0], hr_bpm: [140, 160, 165], elevation_m: [0, 0, 0] } }),
    }))
    render(<RideDetail id="icu_9" />)
    expect(await screen.findByText("5:00 /km")).toBeTruthy()
    expect(screen.getByText("Time in heart-rate zones")).toBeTruthy()
    expect(screen.getByText("Zone 3")).toBeTruthy()
    expect(screen.getByRole("img", { name: "Heart rate over the run" })).toBeTruthy()
    expect(screen.queryByText("Average power")).toBeNull()
    expect(screen.queryByText("Time in power zones")).toBeNull()
    expect(screen.queryByRole("img", { name: /Power/ })).toBeNull()
    expect(screen.getByRole("button", { name: "Review this run" })).toBeTruthy()
  })

  it("shows distance in metres and pace per 100 m for a swim", async () => {
    mock(routes({
      "/api/ride/icu_9/detail": () => json({ ride_id: "icu_9", name: "Pool", sport: "Swim", started_at: "2026-10-11T08:00:00", duration_s: 2000, distance_km: 2, avg_hr: 130, tss: 40 }),
    }))
    render(<RideDetail id="icu_9" />)
    expect(await screen.findByText("2000 m")).toBeTruthy()
    expect(screen.getByText("1:40 /100 m")).toBeTruthy()
    expect(screen.queryByText("Climbing")).toBeNull()
  })

  it("marks a ride as a race and reports a failure", async () => {
    let status = 204
    const calls = mock(routes({
      "/api/ride/icu_9/detail": () => json({ ...RIDE, activity_id: "i123", is_race: false }),
      "/api/activity/i123/race": () => new Response(status === 204 ? null : JSON.stringify({ error: "activity not found" }), { status }),
    }))
    render(<RideDetail id="icu_9" />)
    await userEvent.click(await screen.findByRole("checkbox", { name: "Mark as a race" }))
    expect((await screen.findByRole("status")).textContent).toContain("Marked as a race.")
    expect(calls.find((c) => c.url === "/api/activity/i123/race")?.body).toEqual({ is_race: true })
    status = 404
    await userEvent.click(screen.getByRole("checkbox", { name: "Mark as a race" }))
    expect((await screen.findByRole("alert")).textContent).toContain("activity not found")
  })

  it("saves, validates and clears the effort rating", async () => {
    const calls = mock(routes({ "/api/ride/icu_9/rpe": () => json({ ok: true }) }))
    render(<RideDetail id="icu_9" />)
    const input = (await screen.findByLabelText(/How hard was it/)) as HTMLInputElement
    expect(input.value).toBe("6")
    await userEvent.clear(input)
    await userEvent.type(input, "11")
    expect(screen.getByText("The rating must be between 0 and 10.")).toBeTruthy()
    expect((screen.getByRole("button", { name: "Save rating" }) as HTMLButtonElement).disabled).toBe(true)
    await userEvent.clear(input)
    await userEvent.type(input, "8")
    await userEvent.click(screen.getByRole("button", { name: "Save rating" }))
    expect((await screen.findByText("Rating saved.")).textContent).toBeTruthy()
    expect(calls.find((c) => c.url.endsWith("/rpe"))!.body).toEqual({ rpe: 8 })
    await userEvent.click(screen.getByRole("button", { name: "Clear" }))
    await waitFor(() => expect(calls.filter((c) => c.url.endsWith("/rpe")).at(-1)!.body).toEqual({ rpe: null }))
  })

  it("deletes an imported ride only after a confirmation, using the file name", async () => {
    const calls = mock({
      "/api/ride/fit_2026-10-11T08-00-00/detail": () => json({ ...RIDE, ride_id: "fit_2026-10-11T08-00-00" }),
      "/api/ride/fit_2026-10-11T08-00-00/ftp-test-analysis": () => json({ error: "not found" }, 404),
      "/api/rides/2026-10-11T08-00-00": () => json({ ok: true }),
    })
    render(<RideDetail id="fit_2026-10-11T08-00-00" />)
    await userEvent.click(await screen.findByRole("button", { name: "Delete ride…" }))
    expect(calls.some((c) => c.method === "DELETE")).toBe(false)
    await userEvent.click(screen.getByRole("button", { name: "Yes, delete this ride" }))
    expect((await screen.findByRole("status")).textContent).toBe("Ride deleted.")
    expect(calls.find((c) => c.method === "DELETE")!.url).toBe("/api/rides/2026-10-11T08-00-00")
  })

  it("offers to apply, keep or change FTP after a test and records the verdict", async () => {
    const calls = mock(routes({
      "/api/ride/icu_9/ftp-test-analysis": () => json({ ok: true, ride_id: "icu_9", suggestion: { ftp: 268.4, method: "ramp" }, prior_ftp: 250, halted: false, windows: [{ label: "best sustained minute (scored)", start_s: 600, end_s: 660 }], series: [] }),
      "/api/profile/update-ftp": () => json({ ok: true, ftp: 268 }),
      "/api/ride/icu_9/ftp-test-review": () => json({ ok: true }),
    }))
    render(<RideDetail id="icu_9" />)
    expect(await screen.findByText(/ramp test suggests/)).toBeTruthy()
    expect(screen.getByText(/current FTP 250 W/)).toBeTruthy()
    await userEvent.click(screen.getByRole("button", { name: "Use 268 W" }))
    expect((await screen.findByText("FTP is now 268 W.")).textContent).toBeTruthy()
    expect(calls.find((c) => c.url === "/api/profile/update-ftp")!.body).toEqual({ ftp: 268, method: "ramp", source: "tested_ramp", applied: true })
    expect(calls.find((c) => c.url.endsWith("/ftp-test-review"))!.body).toEqual({ action: "accepted", ftp: 268 })
    await userEvent.click(screen.getByRole("button", { name: "Keep current FTP" }))
    await waitFor(() => expect(calls.filter((c) => c.url.endsWith("/ftp-test-review")).at(-1)!.body).toEqual({ action: "declined", ftp: 268 }))
    expect(calls.filter((c) => c.url === "/api/profile/update-ftp").at(-1)!.body).toMatchObject({ applied: false })
    await userEvent.type(screen.getByLabelText(/Another value/), "700")
    expect((screen.getByRole("button", { name: "Set it" }) as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByText("FTP must be between 50 and 600 W.")).toBeTruthy()
  })

  it("shows a failed load with a retry", async () => {
    mock({ "/api/ride/icu_9/detail": () => json({ error: "Ride not found" }, 404), "/api/ride/icu_9/ftp-test-analysis": () => json({}, 404) })
    render(<RideDetail id="icu_9" />)
    expect((await screen.findAllByRole("alert"))[0].textContent).toContain("Ride not found")
  })
})

describe("Records", () => {
  it("shows new records with links, and nothing when the queue is empty", async () => {
    mock({ "/api/profile/pr-toast-queue": () => json({ queue: [{ ride_id: "icu_9", started_at: "2026-10-11T08:00:00", n_prs: 2 }], count: 1 }) })
    const { unmount } = render(<Records />)
    expect(await screen.findByText(/2 new records/)).toBeTruthy()
    expect(screen.getByRole("link").getAttribute("href")).toBe("#/ride/icu_9")
    unmount()
    mock({ "/api/profile/pr-toast-queue": () => json({ queue: [], count: 0 }) })
    const { container } = render(<Records />)
    await waitFor(() => expect(container.textContent).toBe(""))
  })
})
