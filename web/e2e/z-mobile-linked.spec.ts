import { expect, test, type Page } from "@playwright/test"

// Phone layout (#130) for the screens z-mobile.spec.ts does not reach: the ones opened from a link, not the section bar.
test.describe.configure({ mode: "serial" })

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


const ROUTES = ["builder", "races", "injury", "gear", "fueling", "strength", "onboarding", "setup", "profile-picker"]

for (const phone of PHONES) {
  test.describe(`phone ${phone.width}px, linked screens`, () => {
    test.use({ viewport: phone })
    for (const route of ROUTES) {
      test(`${route} has no sideways scroll and thumb-sized controls`, async ({ page }) => {
        await page.goto(`#/${route}`)
        await page.waitForLoadState("networkidle")
        await expect(page.getByText(/Loading…/)).toHaveCount(0)
        const a = await phoneAudit(page)
        expect(a.pageWidth).toBeLessThanOrEqual(a.vw)
        expect(a.overflowing).toEqual([])
        expect(a.small).toEqual([])
      })
    }
  })
}
