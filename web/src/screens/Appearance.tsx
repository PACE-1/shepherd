import { Card, CardContent } from "@/components/ui/card"
import { useTheme } from "@/components/theme-provider"
import { PALETTES } from "@/lib/palettes"
import { cn } from "@/lib/utils"

const MODES = [
  { id: "system", label: "System" },
  { id: "light", label: "Light" },
  { id: "dark", label: "Dark" },
] as const

// Each half applies the palette's own tokens, so the preview needs no colour table of its own.
function Half({ palette, dark }: { palette: string; dark: boolean }) {
  return (
    <div data-palette={palette === "default" ? undefined : palette} className={cn("flex flex-1 items-center gap-1 bg-background p-2", dark && "dark")}>
      <span className="size-3 rounded-full bg-primary" />
      <span className="size-3 rounded-full bg-[var(--chart-2)]" />
      <span className="size-3 rounded-full bg-[var(--chart-5)]" />
      <span className="h-3 flex-1 rounded bg-muted" />
    </div>
  )
}

export function Appearance() {
  const { theme, setTheme, palette, setPalette } = useTheme()
  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <h2 className="text-sm font-semibold">Appearance</h2>
        <div role="radiogroup" aria-label="Mode" className="flex gap-2">
          {MODES.map((m) => (
            <button key={m.id} type="button" role="radio" aria-checked={theme === m.id} onClick={() => setTheme(m.id)} className={cn("rounded-md border px-3 py-1 text-sm", theme === m.id && "border-ring bg-accent")}>
              {m.label}
            </button>
          ))}
        </div>
        <div role="radiogroup" aria-label="Colour scheme" className="grid grid-cols-2 gap-2">
          {PALETTES.map((p) => (
            <button key={p.id} type="button" role="radio" aria-checked={palette === p.id} onClick={() => setPalette(p.id)} className={cn("overflow-hidden rounded-md border text-left text-sm", palette === p.id && "ring-2 ring-ring")}>
              <span className="flex border-b" aria-hidden>
                <Half palette={p.id} dark={false} />
                <Half palette={p.id} dark />
              </span>
              <span className="block px-2 py-1">{p.label}</span>
            </button>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
