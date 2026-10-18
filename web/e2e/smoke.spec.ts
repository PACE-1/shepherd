import { expect, test, type APIRequestContext } from "@playwright/test"

// One real browser, one real backend on a throwaway data root. The tests run in
// order and build on each other: first-run setup, a second profile, switching,
// then the DFA tab and keyboard navigation.
test.describe.configure({ mode: "serial" })

const api = (request: APIRequestContext, path: string) =>
  request.get(new URL(path, "http://127.0.0.1:" + (process.env.E2E_PORT ?? 22488)).toString())

test("first-run setup walks four steps and saves only what was touched", async ({ page, request }) => {
  await page.goto("#/setup")
  await page.getByRole("button", { name: "Continue without intervals.icu" }).click()
  await page.getByLabel("FTP — Functional Threshold Power (watts)").fill("265")
  await page.getByRole("button", { name: "Next" }).click()
  await page.getByRole("button", { name: "Next" }).click()
  await page.getByRole("button", { name: "Complete Setup" }).click()
  await expect(page.getByText("Setup complete!")).toBeVisible()
  const profiles = await (await api(request, "/api/profiles")).json()
  const active = profiles.profiles.find((p: { id: string }) => p.id === profiles.active)
  expect(active.ftp).toBe(265)
})

test("an out-of-range value blocks Next with a message", async ({ page }) => {
  await page.goto("#/setup")
  await page.getByRole("button", { name: "Continue without intervals.icu" }).click()
  await page.getByLabel("FTP — Functional Threshold Power (watts)").fill("9000")
  await expect(page.getByText("Must be between 50 and 600")).toBeVisible()
  await expect(page.getByRole("button", { name: "Next" })).toBeDisabled()
})

test("the new-profile wizard creates and activates a profile", async ({ page, request }) => {
  await page.goto("#/profile-setup")
  await page.getByLabel("Display Name").fill("Anna")
  await page.getByRole("button", { name: "Next" }).click()
  await page.getByRole("button", { name: "Create profile" }).click()
  await expect(page.getByText("Your training data")).toBeVisible()
  const profiles = await (await api(request, "/api/profiles")).json()
  expect(profiles.active).toBe("anna")
  expect(profiles.profiles.map((p: { name: string }) => p.name)).toContain("Anna")
})

test("the picker lists riders and keyboard activation switches profile", async ({ page, request }) => {
  await page.goto("#/profile-picker")
  await expect(page.getByLabel("Ride as Anna")).toBeVisible()
  // The first profile is named after the OS user, so read the name rather than assume it.
  const first = (await (await api(request, "/api/profiles")).json()).profiles.find((p: { id: string }) => p.id === "default")
  await expect(page.getByLabel(`Ride as ${first.name}`)).toBeVisible()
  await page.getByLabel(`Ride as ${first.name}`).focus()
  await page.keyboard.press("Enter")
  await expect.poll(async () => (await (await api(request, "/api/profiles")).json()).active).toBe("default")
})

test("deleting needs the typed confirmation", async ({ page, request }) => {
  await page.goto("#/profile-picker")
  await page.getByLabel("Settings for Anna").click()
  const del = page.getByRole("button", { name: "Delete account" })
  await expect(del).toBeDisabled()
  await page.getByLabel("Type DELETE to enable deletion").fill("DELETE")
  await del.click()
  await expect.poll(async () =>
    (await (await api(request, "/api/profiles")).json()).profiles.map((p: { id: string }) => p.id),
  ).not.toContain("anna")
})

test("navigation is keyboard reachable and marks the current section", async ({ page }) => {
  await page.goto("#/dfa")
  const nav = page.getByRole("navigation", { name: "Sections" })
  await expect(nav.getByRole("link", { name: "DFA α1" })).toHaveAttribute("aria-current", "page")
  await nav.getByRole("link", { name: "Home" }).focus()
  await page.keyboard.press("Tab")
  await expect(nav.getByRole("link", { name: "Workout Shuffle" })).toBeFocused()
  await page.keyboard.press("Enter")
  await expect(nav.getByRole("link", { name: "Workout Shuffle" })).toHaveAttribute("aria-current", "page")
  await expect(page.getByRole("heading", { name: "Workout shuffle" })).toBeVisible()
})

test("the DFA tab shows its empty state, and a failed load says so", async ({ page }) => {
  await page.goto("#/dfa")
  await expect(page.getByText("No thresholds detected yet.")).toBeVisible()
  await page.route("**/api/profile/dfa-rides", (r) => r.fulfill({ status: 500, body: "{}" }))
  await page.reload()
  await expect(page.getByText("Failed to load DFA data (500)")).toBeVisible()
})

test("Home shows the plan, this week and fitness from the typed reads", async ({ page, request }) => {
  const base = "http://127.0.0.1:" + (process.env.E2E_PORT ?? 22488)
  const gen = await request.post(base + "/api/plan/generate", {
    data: { goal_type: "ftp", hours_per_week: 8, plan_weeks: 8, available_days: [0, 1, 2, 3, 4, 5, 6], rest_days: [] },
  })
  expect(gen.ok()).toBeTruthy()
  await page.goto("#/home")
  await expect(page.getByRole("heading", { name: "Today" })).toBeVisible()
  await expect(page.getByText(/TSS planned/)).toBeVisible()
  await expect(page.getByText("FTP", { exact: true }).first()).toBeVisible()
  await expect(page.getByText(/Loading…/)).toHaveCount(0)
})

test("Plan lists the generated weeks and steps through them", async ({ page }) => {
  await page.goto("#/plan")
  await expect(page.getByRole("heading", { name: /^Week \d+/ })).toBeVisible()
  await expect(page.getByText(/TSS planned/)).toBeVisible()
  const next = page.getByRole("button", { name: "Next week" })
  await next.click()
  await expect(page.getByRole("heading", { name: /^Week \d+/ })).toBeVisible()
})

test("a session can be dismissed and restored from the Plan", async ({ page }) => {
  await page.goto("#/plan")
  await page.getByRole("button", { name: /^Dismiss / }).first().click()
  await expect(page.getByText(/· dismissed/).first()).toBeVisible()
  await page.getByRole("button", { name: /^Restore / }).first().click()
  await expect(page.getByText(/· dismissed/)).toHaveCount(0)
})

test("a session's type can be changed from the Plan", async ({ page }) => {
  await page.goto("#/plan")
  await page.getByRole("button", { name: /^Change type / }).first().click()
  await page.getByLabel("New type").selectOption("tempo")
  await page.getByLabel("Minutes").fill("60")
  await page.getByRole("button", { name: "Apply" }).click()
  await expect(page.getByLabel("New type")).toHaveCount(0)
  await expect(page.getByRole("alert")).toHaveCount(0)
})

test("the Plan can be replaced by a new one built from the form", async ({ page, request }) => {
  await page.goto("#/plan")
  await page.getByRole("button", { name: "Replace the plan…" }).click()
  await page.getByLabel("Goal").selectOption("ftp")
  await page.getByLabel("Plan length (weeks)").fill("6")
  await page.getByRole("button", { name: "Replace plan" }).click()
  await expect(page.getByText(/6 weeks/)).toBeVisible()
  const plan = await (await request.get("http://127.0.0.1:" + (process.env.E2E_PORT ?? 22488) + "/api/plan")).json()
  expect(plan.plan_json.weeks.length).toBeGreaterThanOrEqual(6)
})

test("time off can be recorded and the plan rebuilt around it", async ({ page, request }) => {
  await page.goto("#/plan")
  await page.getByRole("button", { name: "Time off…" }).click()
  const day = (n: number) => { const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10) }
  await page.getByLabel("First day").fill(day(3))
  await page.getByLabel("Last day").fill(day(5))
  await page.getByLabel("Reason").selectOption("illness")
  await page.getByRole("button", { name: "Save and rebuild plan" }).click()
  await expect(page.getByRole("button", { name: "Time off…" })).toBeVisible()
  await expect(page.getByRole("alert")).toHaveCount(0)
  const plan = await (await request.get("http://127.0.0.1:" + (process.env.E2E_PORT ?? 22488) + "/api/plan")).json()
  expect(plan.plan_json.unavailable_periods.at(-1)).toMatchObject({ start: day(3), end: day(5), type: "illness" })
})

const BASE = "http://127.0.0.1:" + (process.env.E2E_PORT ?? 22488)
const dayOffset = (n: number) => { const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10) }

test("Home shows readiness and a daily check-in can be saved", async ({ page, request }) => {
  await page.goto("#/home")
  await expect(page.getByRole("heading", { name: "Readiness" })).toBeVisible()
  await expect(page.getByRole("heading", { name: "Daily check-in" })).toBeVisible()
  await page.getByLabel("Fatigue").selectOption("2")
  await page.getByRole("button", { name: "Save check-in" }).click()
  await expect(page.getByText(/Logged today · wellness/)).toBeVisible()
  const log = await (await request.get(BASE + "/api/daily-log")).json()
  expect(log.today.fatigue).toBe(5) // a rating of 2 of 5 is 5 on the server's Hooper scale
})

test("a race can be added to the Plan", async ({ page, request }) => {
  await page.goto("#/plan")
  await page.getByRole("button", { name: "Add a race…" }).click()
  await page.getByLabel("Race date").fill(dayOffset(35))
  await page.getByLabel("Name").fill("Club crit")
  await page.getByRole("button", { name: "Add race and reshape plan" }).click()
  await expect(page.getByRole("button", { name: "Add a race…" })).toBeVisible()
  await expect(page.getByRole("alert")).toHaveCount(0)
  const plan = await (await request.get(BASE + "/api/plan")).json()
  expect(plan.plan_json.goal.events.some((e: { name: string }) => e.name === "Club crit")).toBe(true)
})

test("availability for the week can be saved", async ({ page, request }) => {
  await page.goto("#/plan")
  await page.getByRole("button", { name: "Availability…" }).click()
  await page.getByRole("spinbutton").first().fill("1.5")
  await page.getByRole("button", { name: "Save availability" }).click()
  await expect(page.getByRole("button", { name: "Availability…" })).toBeVisible()
  await expect(page.getByRole("alert")).toHaveCount(0)
  const plan = await (await request.get(BASE + "/api/plan")).json()
  expect(Object.values(plan.plan_json.availability as Record<string, { hours: number }>).some((a) => a.hours === 1.5)).toBe(true)
})

test("rides can be matched against the week", async ({ page }) => {
  await page.goto("#/plan")
  await page.getByRole("button", { name: "Match rides…" }).click()
  await page.getByRole("button", { name: "Check this week against my rides" }).click()
  await expect(page.getByRole("button", { name: "Save these matches" })).toBeVisible()
  await page.getByRole("button", { name: "Save these matches" }).click()
  await expect(page.getByRole("button", { name: "Match rides…" })).toBeVisible()
  await expect(page.getByRole("alert")).toHaveCount(0)
})

test("another workout can be picked for a day", async ({ page }) => {
  await page.goto("#/plan")
  await page.getByRole("button", { name: /^Other workout / }).first().click()
  await page.getByRole("button", { name: "Find another workout" }).click()
  await page.getByRole("button", { name: "Use this" }).click()
  await expect(page.getByRole("button", { name: "Use this" })).toHaveCount(0)
  await expect(page.getByRole("alert")).toHaveCount(0)
})

test("an FTP-test session gets a test type", async ({ page, request }) => {
  await page.goto("#/plan")
  await page.getByRole("button", { name: /^Change type / }).first().click()
  await page.getByLabel("New type").selectOption("ftp_test")
  await page.getByLabel("Minutes").fill("60")
  await page.getByRole("button", { name: "Apply" }).click()
  await expect(page.getByLabel("New type")).toHaveCount(0)
  await page.getByLabel(/^Test type /).first().selectOption("ramp")
  await expect(page.getByRole("alert")).toHaveCount(0)
  const plan = await (await request.get(BASE + "/api/plan")).json()
  const types = plan.plan_json.weeks.flatMap((w: { sessions: { ftp_test_type?: string }[] }) => w.sessions.map((s) => s.ftp_test_type))
  expect(types).toContain("ramp")
})

test("the Library lists workouts, filters them, and opens one", async ({ page }) => {
  await page.goto("#/library")
  await expect(page.getByText(/^Showing \d+ of \d+/)).toBeVisible()
  await page.getByLabel("Search").fill("recovery")
  await expect(page.getByText(/^Showing \d+ of \d+/)).toBeVisible()
  const first = page.getByRole("listitem").first().getByRole("button")
  await first.click()
  await expect(page.getByRole("img", { name: /^Power profile/ })).toBeVisible()
  await expect(page.getByRole("link", { name: "Download .zwo" })).toBeVisible()
})

test("Workout shuffle suggests workouts", async ({ page }) => {
  await page.goto("#/picker")
  await page.getByRole("button", { name: "Suggest workouts" }).click()
  await expect(page.getByRole("listitem").first()).toBeVisible()
  await expect(page.getByRole("alert")).toHaveCount(0)
  await expect(page.getByRole("button", { name: "Shuffle again" })).toBeVisible()
})

test("Analysis shows its cards with empty states and no errors", async ({ page }) => {
  await page.goto("#/analysis")
  await expect(page.getByRole("heading", { name: "Fitness and form" })).toBeVisible()
  await expect(page.getByRole("heading", { name: "Power curve" })).toBeVisible()
  await expect(page.getByRole("heading", { name: "Recent rides" })).toBeVisible()
  await expect(page.getByText(/No fitness data|Latest \(/)).toBeVisible()
  await expect(page.getByText(/Loading…/)).toHaveCount(0)
  await expect(page.getByRole("alert")).toHaveCount(0)
})

test("Settings saves a changed value and shows the zones", async ({ page, request }) => {
  await page.goto("#/settings")
  await expect(page.getByRole("heading", { name: "Rider" })).toBeVisible()
  await expect(page.getByText("Power zones", { exact: true })).toBeVisible()
  const weight = page.getByLabel("Weight (kg)")
  await weight.fill("72.5")
  await page.getByRole("button", { name: "Save changes" }).click()
  await expect(page.getByRole("status")).toHaveText("Saved.")
  const s = await (await request.get(BASE + "/api/settings")).json()
  expect(s.weight).toBe(72.5)
  await weight.fill("5")
  await expect(page.getByText(/Weight must be between/)).toBeVisible()
  await expect(page.getByRole("button", { name: "Save changes" })).toBeDisabled()
})

test("Settings shows the version and says intervals.icu is not connected", async ({ page }) => {
  await page.goto("#/settings")
  await expect(page.getByRole("heading", { name: "About" })).toBeVisible()
  await expect(page.getByText("Data folder")).toBeVisible()
  await expect(page.getByText(/Not connected/)).toBeVisible()
  await expect(page.getByRole("button", { name: "Sync now" })).toBeDisabled()
})

test("a FIT ride can be imported, rated, downloaded and deleted", async ({ page }) => {
  await page.goto("#/analysis")
  await page.locator('input[type="file"]').setInputFiles("e2e/fixtures/ride.fit")
  await page.getByRole("button", { name: "Import ride" }).click()
  await expect(page.getByRole("status").filter({ hasText: "Ride imported." })).toBeVisible()
  await page.getByRole("link", { name: "Open it" }).click()
  await expect(page.getByRole("link", { name: "Download .fit" })).toBeVisible()
  await page.getByLabel(/How hard was it/).fill("7")
  await page.getByRole("button", { name: "Save rating" }).click()
  await expect(page.getByText("Rating saved.")).toBeVisible()
  await page.getByRole("button", { name: "Delete ride…" }).click()
  await page.getByRole("button", { name: "Yes, delete this ride" }).click()
  await expect(page.getByText("Ride deleted.")).toBeVisible()
})

test("syncing rides without intervals.icu says it is not connected", async ({ page }) => {
  await page.goto("#/analysis")
  await page.getByRole("button", { name: "Sync from intervals.icu" }).click()
  await expect(page.getByRole("status").filter({ hasText: /not connected/ })).toBeVisible()
})

test("Home takes a manual HRV reading and shows body and performance", async ({ page }) => {
  await page.goto("#/home")
  await expect(page.getByRole("heading", { name: "Heart-rate variability" })).toBeVisible()
  await page.getByLabel(/Today’s rMSSD/).fill("64")
  await page.getByRole("button", { name: "Save", exact: true }).click()
  await expect(page.getByRole("status").filter({ hasText: "Saved 64 ms" })).toBeVisible()
  await expect(page.getByRole("heading", { name: "Body and performance" })).toBeVisible()
  await expect(page.getByText(/Loading…/)).toHaveCount(0)
})

test("Settings sets FTP and records it in the history", async ({ page, request }) => {
  await page.goto("#/settings")
  await expect(page.getByRole("heading", { name: "FTP history" })).toBeVisible()
  await page.getByLabel("Set FTP (W)").fill("241")
  await page.getByRole("button", { name: "Set FTP", exact: true }).click()
  await expect(page.getByText("FTP is now 241 W.")).toBeVisible()
  const h = await (await request.get(BASE + "/api/profile/ftp-history")).json()
  expect(h.ftp_current).toBe(241)
})

test("Analysis shows the energy-system card", async ({ page }) => {
  await page.goto("#/analysis")
  await expect(page.getByRole("heading", { name: "Energy systems" })).toBeVisible()
  await expect(page.getByText(/rides have energy-system data|No energy-system data yet/).first()).toBeVisible()
  await expect(page.getByRole("alert")).toHaveCount(0)
})

test("Settings edits and resets custom power zones", async ({ page, request }) => {
  await page.goto("#/settings")
  await page.getByRole("button", { name: "Edit power zones" }).click()
  await page.getByLabel("Power Z1 high").fill("100")
  await page.getByRole("button", { name: "Save zones" }).click()
  await expect(page.getByRole("button", { name: "Edit power zones" })).toBeVisible()
  const custom = await (await request.get(BASE + "/api/settings")).json()
  expect(custom.power_zones[0].high).toBe(100)
  await page.getByRole("button", { name: "Edit power zones" }).click()
  await page.getByRole("button", { name: "Use automatic zones" }).click()
  await expect(page.getByRole("button", { name: "Edit power zones" })).toBeVisible()
  const auto = await (await request.get(BASE + "/api/settings")).json()
  expect(auto.power_zones[0].high).not.toBe(100)
})

test("Settings refuses a folder outside the home folder and offers to connect intervals.icu", async ({ page }) => {
  await page.goto("#/settings")
  await expect(page.getByText(/always included/)).toBeVisible()
  await page.getByLabel(/Folder with your own/).fill("/definitely/outside/home")
  await page.getByRole("button", { name: "Add folder" }).click()
  await expect(page.getByRole("alert").filter({ hasText: /inside your home folder/ })).toBeVisible()
  // This server has no OAuth secret, so the only way to connect is an API key.
  await expect(page.getByRole("link", { name: "Connect intervals.icu" })).toHaveCount(0)
  await page.getByRole("button", { name: "Connect with an API key" }).click()
  await page.getByLabel("API key", { exact: true }).fill("not-a-real-key")
  await expect(page.getByRole("button", { name: "Connect", exact: true })).toBeEnabled()
  await expect(page.getByText("Connect intervals.icu first.")).toBeVisible()
})

test("Settings diagnostics runs a health check", async ({ page }) => {
  await page.goto("#/settings")
  await page.getByRole("button", { name: "Check health" }).click()
  await expect(page.getByRole("status").filter({ hasText: /Every check passed|need attention/ })).toBeVisible()
})

test("Plan shows a calendar, and a session can be dragged to another day of its week", async ({ page, request }) => {
  await request.post(BASE + "/api/plan/generate", { data: { goal: "ftp", hours_per_week: 8, plan_weeks: 8, rest_days: [] } })
  await page.goto("#/plan")
  await page.getByRole("button", { name: "Calendar" }).click()
  await expect(page.getByRole("heading", { name: "Calendar" })).toBeVisible()
  const cells = page.getByRole("group")
  await expect(cells.first()).toBeVisible()
  expect(await cells.count()).toBeGreaterThanOrEqual(7)
  // A future week has all seven days ahead of today, so two draggable days are always there.
  const week = page.locator("section[aria-label^='Week of']").nth(-2)
  const drag = week.locator('[draggable="true"]')
  expect(await drag.count()).toBeGreaterThanOrEqual(2)
  await drag.nth(0).dragTo(drag.nth(1))
  await expect(page.getByRole("status").filter({ hasText: /Moved|Swapped/ })).toBeVisible()
  await expect(page.getByRole("alert")).toHaveCount(0)
  await page.getByRole("button", { name: "Weeks", exact: true }).click()
  await expect(page.getByRole("heading", { name: /^Week \d+/ })).toBeVisible()
})

test("Plan can be updated and its summary image and exports are linked", async ({ page }) => {
  await page.goto("#/plan")
  await page.getByRole("button", { name: "Update plan" }).click()
  await expect(page.getByRole("button", { name: "Update plan" })).toBeEnabled()
  await expect(page.getByRole("alert")).toHaveCount(0)
  await expect(page.getByRole("link", { name: "Summary image" })).toHaveAttribute("href", "/api/programme/summary/png")
  await expect(page.getByRole("link", { name: /Download .zwo/ }).first()).toBeVisible()
  const link = await page.getByRole("link", { name: /Download .zwo/ }).first().getAttribute("href")
  const res = await page.request.get(link!)
  expect(res.ok()).toBeTruthy()
})

test("the plan form takes advanced options and previews the phases", async ({ page }) => {
  await page.goto("#/plan")
  await page.getByRole("button", { name: "Replace the plan…" }).click()
  await page.getByRole("button", { name: "More options…" }).click()
  await page.getByLabel("Intensity mix").selectOption("pyramidal")
  await page.getByRole("button", { name: "Preview the phases" }).click()
  await expect(page.getByLabel(/^base weeks$/)).toBeVisible()
  await page.getByRole("button", { name: "Replace plan" }).click()
  await expect(page.getByText(/\d+ weeks/).first()).toBeVisible()
  await expect(page.getByRole("alert")).toHaveCount(0)
})

test("Analysis shows the training-model cards and the model check runs on request", async ({ page }) => {
  await page.goto("#/analysis")
  await expect(page.getByRole("heading", { name: "Fatigue resistance" })).toBeVisible()
  await expect(page.getByRole("heading", { name: "Your training-load time constants" })).toBeVisible()
  await page.getByRole("button", { name: "Check the model" }).click()
  await expect(page.getByRole("button", { name: "Recompute" })).toBeVisible({ timeout: 60000 })
  await expect(page.getByRole("alert")).toHaveCount(0)
})

test("Library filters by type and downloads the outdoor variant", async ({ page }) => {
  await page.goto("#/library")
  await page.getByLabel(/^Type/).selectOption("threshold")
  await page.getByRole("checkbox", { name: "Outdoor variant for downloads" }).click()
  await expect(page.getByRole("alert")).toHaveCount(0)
  await expect(page.getByRole("button", { name: "Clear filters" })).toBeVisible()
})

test("Home shows this week and last week", async ({ page }) => {
  await page.goto("#/home")
  await expect(page.getByRole("heading", { name: "This week so far" })).toBeVisible()
  await expect(page.getByRole("heading", { name: "Last week" })).toBeVisible()
  await expect(page.getByRole("heading", { name: "DFA α1" })).toBeVisible()
})

test("AI coach: Settings offers a connection, and asking without one points to Settings", async ({ page }) => {
  await page.goto("#/settings")
  await expect(page.getByRole("heading", { name: "AI coach" })).toBeVisible()
  await expect(page.getByText("No provider connected.")).toBeVisible()
  await page.goto("#/home")
  await page.getByLabel("Your question").fill("Am I ready?")
  await page.getByRole("button", { name: "Ask", exact: true }).click()
  await expect(page.getByRole("alert").filter({ hasText: "No AI provider is connected" })).toBeVisible()
  await expect(page.getByRole("link", { name: "Open Settings" })).toBeVisible()
})

test("Settings keeps run and swim thresholds per sport", async ({ page, request }) => {
  await page.goto("#/settings")
  await expect(page.getByRole("heading", { name: "Training load by sport" })).toBeVisible()
  await page.getByLabel(/Swim critical speed/).fill("1:35")
  await page.getByLabel(/Swim critical speed/).locator("..").getByRole("button", { name: "Set", exact: true }).click()
  await expect(page.getByText("Now 1:35 /100 m")).toBeVisible()
  const saved = await (await api(request, "/api/sports/thresholds")).json()
  expect(saved.thresholds.swim_css.current).toBe(95)
})

test("Settings offers the data downloads, and they return files", async ({ page, request }) => {
  await page.goto("#/settings")
  await expect(page.getByRole("heading", { name: "Your data" })).toBeVisible()
  const csv = await api(request, "/api/export/wellness.csv")
  expect(csv.headers()["content-type"]).toContain("text/csv")
  expect(await csv.text()).toContain("date,ctl,atl")
  expect((await api(request, "/api/export/backup")).headers()["content-type"]).toBe("application/gzip")
})

test("Appearance: a palette changes the accent colour and survives a reload", async ({ page }) => {
  const primary = () => page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--primary").trim())
  await page.goto("#/settings")
  await expect(page.getByRole("heading", { name: "Appearance" })).toBeVisible()
  const before = await primary()
  await page.getByRole("radio", { name: "Forest" }).click()
  await expect.poll(primary).not.toBe(before)
  await page.reload()
  await expect(page.locator("html")).toHaveAttribute("data-palette", "forest")
})

test("Notifications: the bell is in the header, and Settings keeps the ntfy address write-only", async ({ page, request }) => {
  await page.goto("#/settings")
  await expect(page.getByRole("heading", { name: "Notifications" })).toBeVisible()
  await page.getByRole("button", { name: "Notifications", exact: true }).click()
  await expect(page.getByText(/Nothing yet/)).toBeVisible()
  await page.getByLabel(/ntfy address/).fill("http://127.0.0.1:9/my-secret-topic")
  await page.getByRole("button", { name: "Save address" }).click()
  await expect(page.getByText("Address saved.")).toBeVisible()
  await page.getByRole("button", { name: "Send a test" }).click()
  await expect(page.getByText(/Could not reach the server/)).toBeVisible()
  await page.getByRole("checkbox", { name: /Missed session/ }).uncheck()
  await expect.poll(async () => (await (await api(request, "/api/notifications/settings")).json()).events.missed).toBe(false)
  const saved = await (await api(request, "/api/notifications/settings")).json()
  expect(saved.has_url).toBe(true)
  expect(JSON.stringify(saved)).not.toContain("secret-topic")
})

test("Home opens with an At a glance panel: status, today's session, the week", async ({ page }) => {
  await page.goto("#/home")
  const glance = page.getByLabel("At a glance")
  await expect(glance.getByRole("heading", { name: "At a glance" })).toBeVisible()
  await expect(glance.getByText(/Ready to train|Take it easy today|Rest today|Not enough data yet/)).toBeVisible()
  await expect(glance.getByRole("heading", { name: "Your session" })).toBeVisible()
  await expect(glance.getByRole("heading", { name: "Your week" })).toBeVisible()
  await expect(glance.getByText("Loading…")).toHaveCount(0)
})

test("Guided setup checks a step before moving on, can skip it, and remembers where you were", async ({ page }) => {
  await page.goto("#/settings")
  await page.getByRole("link", { name: "Run the guided setup" }).click()
  await expect(page.getByRole("heading", { name: "Connect intervals.icu" })).toBeVisible()
  await page.getByRole("button", { name: "Continue" }).click()
  await expect(page.getByRole("alert").filter({ hasText: "not connected yet" })).toBeVisible()
  await page.getByRole("button", { name: "Skip for now" }).click()
  await expect(page.getByRole("heading", { name: "Your rider numbers" })).toBeVisible()
  await page.reload()
  await expect(page.getByRole("heading", { name: "Your rider numbers" })).toBeVisible()
  await expect(page.getByRole("button", { name: /Connect intervals\.icu\s*Skipped/ })).toBeVisible()
})

test("Workout builder: build a session, save it to the Library, and a calendar send without intervals.icu says so", async ({ page, request }) => {
  await page.goto("#/library")
  await page.getByRole("link", { name: "New workout" }).click()
  await expect(page.getByRole("heading", { name: "New workout" })).toBeVisible()
  await page.getByLabel("Name", { exact: true }).fill("E2E over unders")
  await page.getByRole("button", { name: "Add work" }).click()
  await page.getByRole("button", { name: "Move Step 4 up" }).click()
  await expect(page.getByRole("group", { name: "Step 3: Work" })).toBeVisible()
  await expect(page.getByText(/· IF \d\.\d+ · TSS \d+/)).toBeVisible()
  await expect(page.getByRole("img", { name: /Intensity profile/ })).toBeVisible()
  await page.getByRole("button", { name: "Save to library" }).click()
  await expect(page.getByText(/Saved as builder_e2e-over-unders\.zwo/)).toBeVisible()
  const rows = await (await api(request, "/api/workouts?search=e2e")).json()
  expect(rows.map((w: { File: string }) => w.File)).toContain("builder_e2e-over-unders.zwo")
  await page.getByRole("button", { name: "Send to calendar" }).click()
  await expect(page.getByRole("alert").filter({ hasText: "but it wasn’t sent" })).toBeVisible()
  await expect(page.getByRole("alert")).toContainText("isn't connected")
})

test("a critical-speed test sets the run threshold pace and the run zones follow", async ({ page, request }) => {
  await page.goto("#/settings")
  await expect(page.getByRole("heading", { name: "Critical speed test" })).toBeVisible()
  await page.getByLabel("Trial 1 distance (m)").fill("1200")
  await page.getByLabel("Trial 1 time (m:ss)").fill("4:00")
  await page.getByLabel("Trial 2 distance (m)").fill("3600")
  await page.getByLabel("Trial 2 time (m:ss)").fill("14:00")
  await page.getByRole("button", { name: "Calculate" }).click()
  await expect(page.getByText(/Critical speed 4:10 \/km/)).toBeVisible()
  await page.getByRole("button", { name: "Use as threshold pace" }).click()
  await expect(page.getByRole("status").filter({ hasText: "Saved 4:10 /km" })).toBeVisible()
  await expect(page.getByRole("table", { name: "Pace zones" })).toContainText("slower than 5:23 /km")
  const zones = await (await api(request, "/api/run/zones")).json()
  expect(zones.threshold_pace_s_per_km).toBe(250)
})
