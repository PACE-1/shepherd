import { useState } from "react"

import type { NotificationSettings } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { EVENTS, getNotificationSettings, saveNotificationSettings, testNotification, validTime, type EventKey } from "@/lib/notifications"
import { Panel, useLoad } from "@/screens/panel"

const message = (e: unknown) => (e instanceof Error ? e.message : String(e))

function Form({ s, onChange }: { s: NotificationSettings; onChange: () => void }) {
  const [url, setUrl] = useState("")
  const [time, setTime] = useState(s.readiness_time)
  const [events, setEvents] = useState(s.events)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState("")
  const [error, setError] = useState("")
  const run = async (what: () => Promise<string>) => {
    setBusy(true)
    setMsg("")
    setError("")
    try {
      setMsg(await what())
    } catch (e) {
      setError(message(e))
    } finally {
      setBusy(false)
    }
  }
  const toggle = (key: EventKey, on: boolean) => {
    const before = events
    setEvents({ ...events, [key]: on })
    return run(async () => {
      try {
        await saveNotificationSettings({ events: { [key]: on } })
      } catch (e) {
        setEvents(before)
        throw e
      }
      onChange()
      return "Saved."
    })
  }
  const saveTime = () =>
    run(async () => {
      await saveNotificationSettings({ readiness_time: time })
      onChange()
      return "Saved."
    })
  const saveUrl = (value: string) =>
    run(async () => {
      await saveNotificationSettings({ ntfy_url: value })
      setUrl("")
      onChange()
      return value ? "Address saved." : "Address removed."
    })
  const test = () =>
    run(async () => {
      const r = await testNotification()
      if (!r.ok) throw new Error(r.error || "The test message was not delivered.")
      return "Test message sent."
    })
  return (
    <div className="space-y-4 text-sm">
      <p className="text-muted-foreground">
        Notices appear under the bell at the top of every page. You can also have them sent to a phone or computer through{" "}
        <a className="underline" href="https://ntfy.sh" target="_blank" rel="noreferrer">ntfy</a>, hosted or on your own server.
      </p>
      <fieldset className="space-y-2">
        <legend className="mb-1 text-xs font-semibold text-muted-foreground">Send me</legend>
        {EVENTS.map((e) => (
          <Label key={e.key} className="items-start gap-2">
            <input
              type="checkbox"
              className="mt-0.5 size-4 accent-primary"
              checked={events[e.key]}
              onChange={(ev) => toggle(e.key, ev.target.checked)}
            />
            <span>
              {e.label}
              <span className="block text-xs font-normal text-muted-foreground">{e.hint}</span>
            </span>
          </Label>
        ))}
      </fieldset>
      <div className="flex flex-wrap items-end gap-2">
        <Label className="flex-col items-start gap-1">
          Send readiness at (24-hour, empty = first sync of the day)
          <Input className="w-28" value={time} placeholder="07:30" onChange={(e) => setTime(e.target.value.trim())} />
        </Label>
        <Button size="sm" variant="outline" disabled={busy || time === s.readiness_time || !validTime(time)} onClick={saveTime}>
          Set time
        </Button>
        {!validTime(time) && <p role="alert">Use HH:MM, for example 07:30.</p>}
      </div>
      <div className="space-y-2">
        <Label className="flex-col items-start gap-1">
          ntfy address (optional)
          <Input
            className="w-full"
            type="password"
            autoComplete="off"
            value={url}
            placeholder={s.has_url ? "Saved. Type a new address to replace it." : "https://ntfy.sh/your-private-topic"}
            onChange={(e) => setUrl(e.target.value)}
          />
        </Label>
        <p className="text-xs text-muted-foreground">
          The address may contain a secret topic name, so it is stored privately and never shown again. Messages go from this computer to that address and nowhere else.
        </p>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" disabled={busy || !url.trim()} onClick={() => saveUrl(url.trim())}>
            Save address
          </Button>
          <Button size="sm" variant="outline" disabled={busy || !s.has_url} onClick={test}>
            Send a test
          </Button>
          {s.has_url && (
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => saveUrl("")}>
              Remove address
            </Button>
          )}
        </div>
      </div>
      {msg && <p role="status">{msg}</p>}
      {error && <p role="alert">Couldn’t do that: {error}</p>}
    </div>
  )
}

/** Settings card: which notices to get, and where to send them. */
export function NotificationsSettings() {
  const [load, retry, refresh] = useLoad<NotificationSettings>(getNotificationSettings)
  return (
    <Panel title="Notifications" load={load} retry={retry}>
      {(s) => <Form s={s} onChange={refresh} />}
    </Panel>
  )
}
