/// <reference types="node" />
import { cleanup, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { readFileSync } from "node:fs"
import { afterEach, describe, expect, it } from "vitest"

import { ThemeProvider } from "@/components/theme-provider"
import { PALETTES } from "@/lib/palette"
import { Appearance } from "@/screens/Appearance"

afterEach(() => { cleanup(); localStorage.clear(); document.documentElement.removeAttribute("data-palette"); document.documentElement.className = "" })

const luminance = (hex: string) => {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}
const contrast = (a: string, b: string) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

describe("Appearance", () => {
  it("applies and remembers the chosen palette and mode", async () => {
    render(<ThemeProvider><Appearance /></ThemeProvider>)
    await userEvent.click(screen.getByRole("radio", { name: "Ocean" }))
    expect(document.documentElement.getAttribute("data-palette")).toBe("ocean")
    expect(localStorage.getItem("palette")).toBe("ocean")
    expect(screen.getByRole("radio", { name: "Ocean" }).getAttribute("aria-checked")).toBe("true")
    await userEvent.click(screen.getByRole("radio", { name: "Dark" }))
    expect(document.documentElement.classList.contains("dark")).toBe(true)
    await userEvent.click(screen.getByRole("radio", { name: "Graphite" }))
    expect(document.documentElement.hasAttribute("data-palette")).toBe(false)
  })

  it("keeps button text readable (4.5:1) in every palette, light and dark", () => {
    const css = readFileSync("src/index.css", "utf8")
    for (const p of PALETTES.filter((x) => x.id !== "default")) {
      for (const block of [`:root[data-palette="${p.id}"]`, `.dark[data-palette="${p.id}"]`]) {
        const body = css.slice(css.indexOf(block))
        const get = (t: string) => new RegExp(`--${t}: (#[0-9a-f]{6})`).exec(body)![1]
        expect(contrast(get("primary"), get("primary-foreground")), `${block}`).toBeGreaterThanOrEqual(4.5)
      }
    }
  })
})
