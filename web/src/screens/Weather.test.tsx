import { cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { dayLine, placeLabel, resetForecastCache } from "@/lib/weather"
import { readProgress } from "@/lib/onboarding"
import { Onboarding } from "@/screens/Onboarding"
import { LocationCard } from "@/screens/WeatherLocation"
import { SessionWeather } from "@/screens/WeatherSession"

const ATTRIBUTION = { text: "Weather data by Open-Meteo.com", url: "https://open-meteo.com/" }
const BERLIN = { name: "Berlin", region: "Berlin", country: "Germany", latitude: 52.52, longitude: 13.41 }
const DAY = (over: object) => ({
  date: "2026-10-20", rating: "good", reasons: [], suggest_indoor: false, summary: "Partly cloudy", temp_min_c: 8, temp_max_c: 14,
  feels_min_c: 6, feels_max_c: 12, rain_pct_max: 5, rain_mm: 0, gust_max_kmh: 24, wind_max_kmh: 12, ...over,
})
const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })

type Call = { url: string; method: string; body?: unknown }
function mock(routes: Record<string, (init?: RequestInit) => Response>) {
  const calls: Call[] = []
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, method: init?.method ?? "GET", body: init?.body ? JSON.parse(String(init.body)) : undefined })
    const key = Object.keys(routes).find((k) => url === k || url.startsWith(k + "?"))
    return key ? routes[key](init) : json({}, 404)
  }))
  return calls
}
const forecast = (status: string, days: unknown[] = []) => ({ "/api/weather/forecast": () => json({ status, days, attribution: ATTRIBUTION }) })

beforeEach(resetForecastCache)
afterEach(() => { cleanup(); vi.unstubAllGlobals(); localStorage.clear() })

describe("SessionWeather", () => {
  it("shows a good day in words with the numbers and the credit", async () => {
    mock(forecast("ok", [DAY({})]))
    render(<SessionWeather day="2026-10-20" />)
    expect(await screen.findByText("Good conditions")).toBeTruthy()
    expect(screen.getByText(/Partly cloudy, 8 to 14 °C, gusts up to 24 km\/h, rain 5%/)).toBeTruthy()
    const credit = screen.getByRole("link", { name: "Weather data by Open-Meteo.com" })
    expect(credit.getAttribute("href")).toBe("https://open-meteo.com/")
    expect(screen.queryByText(/indoor/)).toBeNull()
  })

  it("flags a poor day with the reason and offers the existing swap flow", async () => {
    mock(forecast("ok", [DAY({ rating: "poor", reasons: ["gusts 58 km/h", "thunderstorms forecast"], suggest_indoor: true })]))
    const onSwap = vi.fn()
    render(<SessionWeather day="2026-10-20" onSwap={onSwap} />)
    expect(await screen.findByText("Poor conditions")).toBeTruthy()
    expect(screen.getByText(/gusts 58 km\/h, thunderstorms forecast/)).toBeTruthy()
    expect(screen.getByText(/Consider an indoor session/)).toBeTruthy()
    await userEvent.click(screen.getByRole("button", { name: "Change type" }))
    expect(onSwap).toHaveBeenCalledOnce()
  })

  it("links to the plan when there is no swap handler (Home)", async () => {
    mock(forecast("ok", [DAY({ rating: "poor", reasons: ["gusts 58 km/h"], suggest_indoor: true })]))
    render(<SessionWeather day="2026-10-20" swapHref="#/plan" />)
    expect((await screen.findByRole("link", { name: /swap it/ })).getAttribute("href")).toBe("#/plan")
  })

  it("shows nothing without a location, for a day outside the forecast, or when the page cannot load it", async () => {
    mock(forecast("no_location"))
    const { container, unmount } = render(<SessionWeather day="2026-10-20" />)
    await waitFor(() => expect(fetch).toHaveBeenCalled())
    expect(container.textContent).toBe("")
    unmount()
    resetForecastCache()
    mock(forecast("ok", [DAY({})]))
    const other = render(<SessionWeather day="2026-11-30" />)
    await waitFor(() => expect(fetch).toHaveBeenCalled())
    expect(other.container.textContent).toBe("")
    other.unmount()
    resetForecastCache()
    mock({})
    const failed = render(<SessionWeather day="2026-10-20" />)
    await waitFor(() => expect(fetch).toHaveBeenCalled())
    expect(failed.container.textContent).toBe("")
  })

  it("says the forecast is unavailable instead of failing", async () => {
    mock(forecast("unavailable"))
    render(<SessionWeather day="2026-10-20" />)
    expect(await screen.findByText("Forecast unavailable")).toBeTruthy()
    expect(screen.queryByRole("alert")).toBeNull()
  })

  it("reads the forecast once for many sessions", async () => {
    const calls = mock(forecast("ok", [DAY({})]))
    render(<><SessionWeather day="2026-10-20" /><SessionWeather day="2026-10-20" /></>)
    await screen.findAllByText("Good conditions")
    expect(calls.filter((c) => c.url === "/api/weather/forecast")).toHaveLength(1)
  })
})

describe("lib", () => {
  it("formats place and day", () => {
    expect(placeLabel(BERLIN)).toBe("Berlin, Berlin, Germany")
    expect(placeLabel({ name: "Leeds", region: "", country: "UK" })).toBe("Leeds, UK")
    expect(dayLine(DAY({ temp_min_c: 9, temp_max_c: 9, gust_max_kmh: null }) as never)).toBe("Partly cloudy, 9 °C, rain 5%")
  })
})

describe("LocationCard", () => {
  const none = { has_location: false, place: null, network_enabled: true }

  it("searches, picks a result and saves it, saying what is sent", async () => {
    const calls = mock({
      "/api/weather/location": (init) => (init?.method === "PUT" ? json({ has_location: true, place: BERLIN, network_enabled: true }) : json(none)),
      "/api/weather/search": () => json({ available: true, message: "", results: [BERLIN, { ...BERLIN, region: "New Hampshire", country: "United States" }] }),
    })
    render(<LocationCard />)
    expect(await screen.findByText(/No location set, so no forecast is shown/)).toBeTruthy()
    expect(screen.getByText(/only the location rounded to about 1 km \(2 decimals\) is sent/)).toBeTruthy()
    await userEvent.type(screen.getByLabelText("Place name"), "Berlin")
    await userEvent.click(screen.getByRole("button", { name: "Search" }))
    expect(calls.some((c) => c.url === "/api/weather/search?q=Berlin")).toBe(true)
    await userEvent.click(await screen.findByRole("button", { name: "Berlin, New Hampshire, United States" }))
    await screen.findByText(/Saved Berlin, New Hampshire, United States/)
    expect(calls.find((c) => c.method === "PUT")?.body).toMatchObject({ name: "Berlin", region: "New Hampshire", latitude: 52.52 })
  })

  it("degrades to a message when place search is unavailable, and 'no location' stays possible", async () => {
    mock({
      "/api/weather/location": () => json(none),
      "/api/weather/search": () => json({ available: false, message: "Place search is unavailable right now (no network, or network use is switched off).", results: [] }),
    })
    render(<LocationCard />)
    await userEvent.type(await screen.findByLabelText("Place name"), "Berlin")
    await userEvent.click(screen.getByRole("button", { name: "Search" }))
    expect((await screen.findByRole("status")).textContent).toMatch(/Place search is unavailable/)
    expect(screen.queryByRole("alert")).toBeNull()
  })

  it("removes a saved location", async () => {
    let has = true
    const calls = mock({
      "/api/weather/location": (init) => {
        if (init?.method === "DELETE") has = false
        return json({ has_location: has, place: has ? BERLIN : null, network_enabled: true })
      },
    })
    render(<LocationCard />)
    expect(await screen.findByText("Berlin, Berlin, Germany")).toBeTruthy()
    await userEvent.click(screen.getByRole("button", { name: "Use no location" }))
    await screen.findByText(/Location removed/)
    expect(calls.some((c) => c.method === "DELETE")).toBe(true)
    expect(await screen.findByText(/No location set/)).toBeTruthy()
  })
})

describe("Onboarding location step", () => {
  it("asks 'Where do you ride?', says why, blocks Continue until a place is picked, and can be skipped", async () => {
    mock({ "/api/weather/location": () => json({ has_location: false, place: null, network_enabled: true }) })
    localStorage.setItem("shepherd_onboarding:", JSON.stringify({ done: ["icu", "rider"], skipped: ["ai", "folders"], finished: false }))
    render(<Onboarding />)
    expect(await screen.findByRole("heading", { name: "Where do you ride?" })).toBeTruthy()
    expect(screen.getByText(/for the weather forecast next to your outdoor sessions/i)).toBeTruthy()
    await userEvent.click(screen.getByRole("button", { name: "Continue" }))
    expect((await screen.findByRole("alert")).textContent).toMatch(/No place picked yet/)
    await userEvent.click(screen.getByRole("button", { name: "Skip this step" }))
    expect(await screen.findByRole("heading", { name: "Goal and weekly availability" })).toBeTruthy()
    expect(readProgress("shepherd_onboarding:").skipped).toContain("location")
  })
})
