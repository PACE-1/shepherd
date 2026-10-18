import { useTheme } from "@/components/theme-provider"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { PALETTES, usePalette } from "@/lib/palette"

const MODES = [
  { id: "light", name: "Light" },
  { id: "dark", name: "Dark" },
  { id: "system", name: "System" },
] as const

/** Light, dark or system, and a colour palette. Each palette has a light and a dark variant. */
export function Appearance() {
  const { theme, setTheme } = useTheme()
  const [palette, setPalette] = usePalette()
  return (
    <Card>
      <CardContent className="space-y-3 p-4 text-sm">
        <h2 className="text-sm font-semibold">Appearance</h2>
        <div role="radiogroup" aria-label="Mode" className="flex gap-2">
          {MODES.map((m) => (
            <Button key={m.id} role="radio" aria-checked={theme === m.id} size="sm" variant={theme === m.id ? "default" : "outline"} onClick={() => setTheme(m.id)}>
              {m.name}
            </Button>
          ))}
        </div>
        <div role="radiogroup" aria-label="Colour palette" className="flex flex-wrap gap-2">
          {PALETTES.map((p) => (
            <button
              key={p.id}
              type="button"
              role="radio"
              aria-checked={palette === p.id}
              onClick={() => setPalette(p.id)}
              className={`flex items-center gap-2 rounded-md border px-3 py-2 ${palette === p.id ? "border-ring ring-2 ring-ring" : "border-border"}`}
            >
              <span aria-hidden className="flex overflow-hidden rounded-full border">
                <span className="size-4" style={{ background: p.light }} />
                <span className="size-4" style={{ background: p.dark }} />
              </span>
              {p.name}
            </button>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
