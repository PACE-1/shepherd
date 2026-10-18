import { useCallback, useEffect, useState } from "react"

export const PALETTES = [
  { id: "default", name: "Graphite", light: "#111111", dark: "#fafafa" },
  { id: "ocean", name: "Ocean", light: "#2563eb", dark: "#60a5fa" },
  { id: "forest", name: "Forest", light: "#15803d", dark: "#4ade80" },
  { id: "sunset", name: "Sunset", light: "#c2410c", dark: "#fb923c" },
  { id: "violet", name: "Violet", light: "#6d28d9", dark: "#a78bfa" },
] as const

export type PaletteId = (typeof PALETTES)[number]["id"]
const KEY = "palette"
const isPalette = (v: string | null): v is PaletteId => PALETTES.some((p) => p.id === v)

export function applyPalette(id: PaletteId) {
  if (id === "default") document.documentElement.removeAttribute("data-palette")
  else document.documentElement.setAttribute("data-palette", id)
}

function stored(): PaletteId {
  try {
    const v = localStorage.getItem(KEY)
    return isPalette(v) ? v : "default"
  } catch {
    return "default"
  }
}

/** Applies the saved palette once at startup, before the first paint of the app. */
export const applyStoredPalette = () => applyPalette(stored())

export function usePalette() {
  const [palette, setState] = useState<PaletteId>(stored)
  useEffect(() => applyPalette(palette), [palette])
  const setPalette = useCallback((id: PaletteId) => {
    try {
      localStorage.setItem(KEY, id)
    } catch {
      /* private mode: the choice lasts until reload */
    }
    setState(id)
  }, [])
  return [palette, setPalette] as const
}
