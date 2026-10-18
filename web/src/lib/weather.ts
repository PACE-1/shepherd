import type { WeatherDay, WeatherForecast, WeatherLocation, WeatherPlace, WeatherSearch } from "@/api/types"
import { api } from "@/lib/api"

// Weather for planned outdoor sessions (#117). The server does the rating; this is the plumbing and the words.

export const ATTRIBUTION = { text: "Weather data by Open-Meteo.com", url: "https://open-meteo.com/" } as const

/** Said wherever a place is chosen: exactly what leaves the machine. */
export const PRIVACY =
  "Your location is stored only in your profile folder. To find a place, the text you type is sent to Open-Meteo. For the forecast, only the location rounded to about 1 km (2 decimals) is sent to Open-Meteo. Nothing else is sent, and the AI coach never sees it."

// One forecast read shared by every session on a screen, kept for 5 minutes (the server caches for an hour).
const CLIENT_SECONDS = 300
let forecastCache: { at: number; promise: Promise<WeatherForecast> } | null = null
export const resetForecastCache = () => { forecastCache = null }
export function getForecast(): Promise<WeatherForecast> {
  if (!forecastCache || Date.now() - forecastCache.at > CLIENT_SECONDS * 1000) {
    const promise = api<WeatherForecast>("/api/weather/forecast")
    forecastCache = { at: Date.now(), promise }
    promise.catch(() => { forecastCache = null })
  }
  return forecastCache.promise
}

export const getLocation = () => api<WeatherLocation>("/api/weather/location")
export const searchPlaces = (q: string) => api<WeatherSearch>(`/api/weather/search?q=${encodeURIComponent(q)}`)
export const saveLocation = (p: WeatherPlace) => {
  resetForecastCache()
  return api<WeatherLocation>("/api/weather/location", { method: "PUT", json: p })
}
export const clearLocation = () => {
  resetForecastCache()
  return api<WeatherLocation>("/api/weather/location", { method: "DELETE" })
}

export const placeLabel = (p: Pick<WeatherPlace, "name" | "region" | "country">) =>
  [p.name, p.region, p.country].filter(Boolean).join(", ")

export const RATING_WORD = { good: "Good conditions", marginal: "Marginal conditions", poor: "Poor conditions" } as const

/** "Partly cloudy, 12 to 17 °C, gusts up to 35 km/h, rain 20%": the numbers on one line. */
export function dayLine(d: WeatherDay): string {
  const t =
    d.temp_min_c != null && d.temp_max_c != null
      ? d.temp_min_c === d.temp_max_c ? `${d.temp_max_c} °C` : `${d.temp_min_c} to ${d.temp_max_c} °C`
      : ""
  return [
    d.summary,
    t,
    d.gust_max_kmh != null ? `gusts up to ${d.gust_max_kmh} km/h` : "",
    d.rain_pct_max != null ? `rain ${d.rain_pct_max}%` : "",
  ].filter(Boolean).join(", ")
}
