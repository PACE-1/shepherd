import { expect, test, type Page } from "@playwright/test"

// Phone layout and installable app (#130). Named z- so it runs after smoke.spec.ts, on the same
// server and the plan, library and settings that file leaves behind (and not in anyone's merge way).
test.describe.configure({ mode: "serial" })

const BASE = "http://127.0.0.1:" + (process.env.E2E_PORT ?? 22488)
const PHONES = [{ width: 360, height: 740 }, { width: 430, height: 932 }]

/** What breaks a phone layout: a page wider than the screen, content poking out of it, and controls too small to tap. */
async function phoneAudit(page: Page) {
  return page.evaluate(() => {
    const vw = window.innerWidth
    const visible = (e: Element) => {
      const r = e.getBoundingClientRect()
      const s = getComputedStyle(e)
      return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none"
    }
    const clipped = (e: Element) => {
      for (let p = e.parentElement; p && p !== document.documentElement; p = p.parentElement) {
        const s = getComputedStyle(p)
        if (s.overflowX !== "visible" && p.getBoundingClientRect().right <= vw + 1) return true
      }
      return false
    }
    const name = (e: Element) => `${e.tagName.toLowerCase()}${e.getAttribute("aria-label") ? `[${e.getAttribute("aria-label")}]` : ""}:${(e.textContent ?? "").trim().slice(0, 24)}`
    const overflowing = [...document.body.querySelectorAll("*")]
      .filter((e) => visible(e) && e.getBoundingClientRect().right > vw + 1 && !clipped(e))
      .slice(0, 8)
      .map(name)
    const small = [...document.querySelectorAll('button, [data-slot="button"], a[download], select, textarea, input:not([type=checkbox]):not([type=radio]):not([type=hidden]):not([type=file]):not([type=range])')]
      .filter((e) => visible(e) && !e.closest('[role="switch"], [role="checkbox"], [role="radio"]'))
      .filter((e) => { const r = e.getBoundingClientRect(); return r.height < 43.5 || r.width < 43.5 })
      .slice(0, 8)
      .map((e) => { const r = e.getBoundingClientRect(); return `${name(e)} ${Math.round(r.width)}x${Math.round(r.height)}` })
    return { pageWidth: document.documentElement.scrollWidth, vw, overflowing, small }
  })
}

for (const phone of PHONES) {
  test.describe(`phone ${phone.width}px`, () => {
    test.use({ viewport: phone })
    for (const route of ["home", "plan", "library", "analysis", "settings", "picker", "dfa"]) {
      test(`${route} has no sideways scroll and thumb-sized controls`, async ({ page }) => {
        await page.goto(`#/${route}`)
        await expect(page.getByRole("navigation", { name: "Sections" })).toBeVisible()
        await page.waitForLoadState("networkidle")
        await expect(page.getByText(/Loading…/)).toHaveCount(0)
        const a = await phoneAudit(page)
        expect(a.pageWidth).toBeLessThanOrEqual(a.vw)
        expect(a.overflowing).toEqual([])
        expect(a.small).toEqual([])
      })
    }

    test("a ride's detail page fits too", async ({ page }) => {
      await page.goto("#/analysis")
      await page.locator('input[type="file"]').setInputFiles("e2e/fixtures/ride.fit")
      await page.getByRole("button", { name: "Import ride" }).click()
      await expect(page.getByRole("status").filter({ hasText: "Ride imported." })).toBeVisible()
      await page.getByRole("link", { name: "Open it" }).click()
      await expect(page.getByRole("link", { name: "Download .fit" })).toBeVisible()
      await page.waitForLoadState("networkidle")
      const a = await phoneAudit(page)
      expect(a.pageWidth).toBeLessThanOrEqual(a.vw)
      expect(a.overflowing).toEqual([])
      expect(a.small).toEqual([])
      await page.getByRole("button", { name: "Delete ride…" }).click()
      await page.getByRole("button", { name: "Yes, delete this ride" }).click()
      await expect(page.getByText("Ride deleted.")).toBeVisible()
    })
  })
}

test("on a phone the section bar sits at the bottom, reaches every screen, and More holds the rest", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto("#/home")
  const nav = page.getByRole("navigation", { name: "Sections" })
  const box = (await nav.boundingBox())!
  expect(box.y + box.height).toBeGreaterThan(844 - 2) // pinned to the bottom edge
  await nav.getByRole("link", { name: "Workout Library" }).click()
  await expect(page).toHaveURL(/#\/library$/)
  await nav.getByRole("button", { name: "More" }).click()
  await page.getByRole("link", { name: "DFA α1" }).click()
  await expect(page).toHaveURL(/#\/dfa$/)
  await expect(page.locator("#more-menu")).toHaveCount(0)
  await nav.getByRole("button", { name: "More" }).click()
  await expect(page.getByRole("link", { name: "Switch rider" })).toBeVisible()
  await expect(page.getByRole("link", { name: "Workout Shuffle" })).toBeVisible()
})

test("on a desktop the section bar stays at the top and More is not shown", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  await page.goto("#/home")
  const nav = page.getByRole("navigation", { name: "Sections" })
  expect((await nav.boundingBox())!.y).toBeLessThan(100)
  await expect(nav.getByRole("button", { name: "More" })).toBeHidden()
  await expect(nav.getByRole("link", { name: "Switch rider" })).toBeVisible()
})

test("the app can be installed: manifest, icons and a shell-only service worker", async ({ page, request }) => {
  const m = await request.get(BASE + "/v2/manifest.webmanifest")
  expect(m.ok()).toBeTruthy()
  expect(m.headers()["content-type"]).toContain("manifest+json")
  const manifest = await m.json()
  expect(manifest).toMatchObject({ name: "Shepherd", display: "standalone", scope: "/v2/" })
  expect(manifest.start_url.startsWith("/v2/")).toBe(true)
  expect(manifest.theme_color).toBeTruthy()
  for (const icon of manifest.icons) {
    const r = await request.get(new URL(icon.src, BASE + "/v2/manifest.webmanifest").toString())
    expect(r.headers()["content-type"], icon.src).toContain("image/png")
  }
  expect(manifest.icons.some((i: { sizes: string }) => i.sizes === "192x192")).toBe(true)
  expect(manifest.icons.some((i: { sizes: string }) => i.sizes === "512x512")).toBe(true)
  const sw = await request.get(BASE + "/v2/sw.js")
  expect(sw.headers()["content-type"]).toContain("javascript")

  await page.goto("#/home")
  await expect(page.locator('link[rel="manifest"]')).toHaveAttribute("href", "/v2/manifest.webmanifest")
  const scope = await page.evaluate(async () => (await navigator.serviceWorker.ready).scope)
  expect(scope).toBe(BASE + "/v2/")
  // The first load is not controlled; a reload is. Then read data through the page and look in the cache.
  await page.reload()
  await expect.poll(() => page.evaluate(() => !!navigator.serviceWorker.controller)).toBe(true)
  await page.evaluate(() => fetch("/api/profiles").then((r) => r.json()))
  await page.evaluate(() => fetch("/api/plan").then((r) => r.status))
  const cached = await page.evaluate(async () => {
    const out: string[] = []
    for (const k of await caches.keys()) for (const r of await (await caches.open(k)).keys()) out.push(new URL(r.url).pathname)
    return out
  })
  expect(cached.length).toBeGreaterThan(0)
  expect(cached.every((p) => p.startsWith("/v2/"))).toBe(true)
  expect(cached.some((p) => p.includes("/api"))).toBe(false)
})
