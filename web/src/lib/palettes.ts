/** Named colour schemes. The token values live in index.css under [data-palette="id"]. */
export const PALETTES = [
  { id: "default", label: "Default" },
  { id: "ocean", label: "Ocean" },
  { id: "forest", label: "Forest" },
  { id: "rose", label: "Rose" },
  { id: "violet", label: "Violet" },
] as const

export type Palette = (typeof PALETTES)[number]["id"]

export const isPalette = (v: string | null): v is Palette => PALETTES.some((p) => p.id === v)
