import { act, cleanup, render, screen } from "@testing-library/react"
import { afterEach, expect, it } from "vitest"

import { useLoad } from "@/screens/panel"

afterEach(cleanup)

function Probe({ fetcher }: { fetcher: () => Promise<string> }) {
  const [load] = useLoad<string>(fetcher)
  return <p>{load.state === "ok" ? `got ${load.data}` : load.state}</p>
}

it("shows the newest request's result even when an older request answers last", async () => {
  let slow!: (v: string) => void
  const first = () => new Promise<string>((r) => { slow = r })
  const second = () => Promise.resolve("new")
  const { rerender } = render(<Probe fetcher={first} />)
  rerender(<Probe fetcher={second} />)
  expect(await screen.findByText("got new")).toBeTruthy()
  await act(async () => { slow("old") })
  expect(screen.getByText("got new")).toBeTruthy()
})
