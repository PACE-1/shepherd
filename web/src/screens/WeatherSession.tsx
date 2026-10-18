import { useEffect, useState } from "react"

import type { WeatherForecast } from "@/api/types"
import { Button } from "@/components/ui/button"
import { ATTRIBUTION, dayLine, getForecast, RATING_WORD } from "@/lib/weather"

/**
 * The forecast for one planned outdoor session, by its day. Shows nothing without a location, and nothing for
 * days outside the 7-day forecast. A poor day suggests an indoor session and offers the existing swap flow.
 * There is no indoor/outdoor flag on plan sessions, so every ride is treated as an outdoor candidate.
 */
export function SessionWeather({ day, onSwap, swapHref }: { day: string; onSwap?: () => void; swapHref?: string }) {
  const [f, setF] = useState<WeatherForecast | null>(null)
  useEffect(() => {
    let live = true
    getForecast().then((x) => live && setF(x), () => live && setF(null))
    return () => { live = false }
  }, [])
  if (!f || f.status === "no_location") return null
  if (f.status !== "ok") return <p className="basis-full text-xs text-muted-foreground">Forecast unavailable</p>
  const d = f.days.find((x) => x.date === day)
  if (!d) return null
  return (
    <div className="basis-full space-y-0.5 text-xs" aria-label={`Weather ${day}`}>
      <p>
        <span className="font-medium">{RATING_WORD[d.rating as keyof typeof RATING_WORD] ?? d.rating}</span>
        {d.reasons.length > 0 && <>: {d.reasons.join(", ")}</>}
        <span className="text-muted-foreground"> · {dayLine(d)}</span>
      </p>
      {d.suggest_indoor && (
        <p>
          Consider an indoor session for this day.{" "}
          {onSwap ? (
            <Button size="sm" variant="link" className="h-auto p-0 text-xs" onClick={onSwap}>
              Change type
            </Button>
          ) : swapHref ? (
            <a className="underline" href={swapHref}>Open Training Plan to swap it</a>
          ) : null}
        </p>
      )}
      <p className="text-muted-foreground">
        <a className="underline" href={f.attribution?.url ?? ATTRIBUTION.url} target="_blank" rel="noopener noreferrer">
          {f.attribution?.text ?? ATTRIBUTION.text}
        </a>
      </p>
    </div>
  )
}
