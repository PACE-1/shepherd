import { Component, useCallback, useEffect, useState, type ReactNode } from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"

export type Load<T> = { state: "loading" } | { state: "ok"; data: T } | { state: "error"; message: string }

// One independent request per card: a failure in one leaves the others usable and is retried alone.
export function useLoad<T>(fetcher: () => Promise<T>) {
  const [value, setValue] = useState<Load<T>>({ state: "loading" })
  const fetchInto = useCallback(() => {
    fetcher().then(
      (data) => setValue({ state: "ok", data }),
      (e: unknown) => setValue({ state: "error", message: e instanceof Error ? e.message : String(e) }),
    )
  }, [fetcher])
  const run = useCallback(() => {
    setValue({ state: "loading" })
    fetchInto()
  }, [fetchInto])
  // Re-reads without flipping to "Loading…", so a card keeps its content (and any message in it) while it refreshes.
  const refresh = useCallback(() => {
    fetcher().then(
      (data) => setValue({ state: "ok", data }),
      () => {},
    )
  }, [fetcher])
  // The state starts as "loading", so the first read only has to fetch.
  useEffect(fetchInto, [fetchInto])
  return [value, run, refresh] as const
}

/** A card that throws while rendering (a response with an unexpected shape) shows a message instead of blanking the page. */
class Guard extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    return this.state.failed ? (
      <p role="alert" className="text-sm">
        This card couldn’t be shown. Reload the page to try again.
      </p>
    ) : (
      this.props.children
    )
  }
}

// The render function runs inside the guard, not before it, so a throw is caught.
function Render<T>({ fn, data }: { fn: (d: T) => ReactNode; data: T }) {
  return <>{fn(data)}</>
}

export function Panel<T>({
  title,
  load,
  retry,
  children,
}: {
  title: string
  load: Load<T>
  retry: () => void
  children: (data: T) => ReactNode
}) {
  return (
    <Card>
      <CardContent className="space-y-2 p-4">
        <h2 className="text-sm font-semibold">{title}</h2>
        {load.state === "loading" && <p className="text-sm text-muted-foreground">Loading…</p>}
        {load.state === "error" && (
          <div role="alert" className="text-sm">
            <p>Couldn’t load this: {load.message}</p>
            <Button className="mt-2" size="sm" variant="outline" onClick={retry}>
              Retry
            </Button>
          </div>
        )}
        {load.state === "ok" && (
          <Guard>
            <Render fn={children} data={load.data} />
          </Guard>
        )}
      </CardContent>
    </Card>
  )
}

export const Row = ({ label, value }: { label: string; value: ReactNode }) => (
  <div className="flex justify-between gap-4 text-sm">
    <dt className="text-muted-foreground">{label}</dt>
    <dd>{value}</dd>
  </div>
)

