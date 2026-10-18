import { cleanup, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, it } from "vitest"

import { ThemeProvider } from "@/components/theme-provider"
import { Appearance } from "@/screens/Appearance"

beforeEach(() => {
  localStorage.clear()
  delete document.documentElement.dataset.palette
  window.matchMedia = ((q: string) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {} })) as never
})
afterEach(cleanup)

it("applies and remembers a colour scheme, and Default clears it", async () => {
  render(<ThemeProvider storageKey="t"><Appearance /></ThemeProvider>)
  await userEvent.click(screen.getByRole("radio", { name: /Ocean/ }))
  expect(document.documentElement.dataset.palette).toBe("ocean")
  expect(localStorage.getItem("t-palette")).toBe("ocean")
  await userEvent.click(screen.getByRole("radio", { name: /Default/ }))
  expect(document.documentElement.dataset.palette).toBeUndefined()
})

it("restores a stored colour scheme and ignores an unknown one", () => {
  localStorage.setItem("t-palette", "forest")
  render(<ThemeProvider storageKey="t"><Appearance /></ThemeProvider>)
  expect(document.documentElement.dataset.palette).toBe("forest")
  cleanup()
  localStorage.setItem("t-palette", "nope")
  delete document.documentElement.dataset.palette
  render(<ThemeProvider storageKey="t"><Appearance /></ThemeProvider>)
  expect(document.documentElement.dataset.palette).toBeUndefined()
})
