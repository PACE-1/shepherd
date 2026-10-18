import { useCallback, useEffect, useState } from "react"

import type { IcuConnection, SettingsRead, SyncStatus, UpdateCheck, VersionInfo, ZoneBand } from "@/api/types"
import { Button, buttonVariants } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/native-select"
import { Input } from "@/components/ui/input"
import { checkUpdate, connectUrl, diff, disconnectIcu, formFrom, getSettings, getSyncStatus, getVersion, saveSettings, syncNow, type RiderForm } from "@/lib/settings"
import { getIcuConnection, getLimits, type Limits } from "@/lib/setup"
import { CalendarPush } from "@/screens/CalendarPush"
import { Diagnostics } from "@/screens/Diagnostics"
import { Folders } from "@/screens/Folders"
import { FolderImport } from "@/screens/FolderImport"
import { ApiKeyConnect } from "@/screens/ApiKeyConnect"
import { AiCoachSettings } from "@/screens/Coach"
import { FtpHistory } from "@/screens/FtpHistory"
import { Appearance } from "@/screens/Appearance"
import { NotificationsSettings } from "@/screens/Notifications"
import { NutritionSettings } from "@/screens/NutritionSettings"
import { SportsCard } from "@/screens/SportsCard"
import { RunZones } from "@/screens/RunZones"
import { RacePredictor } from "@/screens/RacePredictor"
import { SwimSessions } from "@/screens/SwimSessions"
import { SwimZones } from "@/screens/SwimZones"
import { YourData } from "@/screens/YourData"
import { Panel, Row, useLoad } from "@/screens/panel"
import { ZonesEditor } from "@/screens/ZonesEditor"
import { LocationCard } from "@/screens/WeatherLocation"

const Zones = ({ title, zones, unit }: { title: string; zones: ZoneBand[]; unit: string }) => (
  <div>
    <h3 className="text-xs font-semibold text-muted-foreground">{title}</h3>
    <dl className="space-y-0.5">
      {zones.map((z) => (
        <Row key={z.zone} label={z.name || z.zone} value={z.high >= 9999 ? `${z.low}+ ${unit}` : `${z.low} to ${z.high} ${unit}`} />
      ))}
    </dl>
  </div>
)

function RiderForm_({ s, limits, saved }: { s: SettingsRead; limits: Limits; saved: (now: SettingsRead) => void }) {
  const [f, setF] = useState<RiderForm>(() => formFrom(s))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const { changes, problems } = diff(s, f, limits)
  const dirty = Object.keys(changes).length > 0
  const set = (k: keyof RiderForm, v: string) => setF({ ...f, [k]: v } as RiderForm)

  const submit = async () => {
    setBusy(true)
    setError("")
    try {
      saved((await saveSettings(changes)).settings)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }
  const field = (k: "weight" | "ftp" | "lthr" | "maxHr", label: string) => (
    <Label className="flex-col items-start gap-1">
      {label}
      <Input type="number" className="w-28" value={f[k]} onChange={(e) => set(k, e.target.value)} />
    </Label>
  )
  return (
    <div className="space-y-3 text-sm">
      <div className="flex flex-wrap items-end gap-3">
        {field("weight", "Weight (kg)")}
        {field("ftp", "FTP (W)")}
        {field("lthr", "LTHR (bpm)")}
        {field("maxHr", "Max HR (bpm)")}
        <Label className="flex-col items-start gap-1">
          Targets
          <NativeSelect  value={f.targetMode} onChange={(e) => set("targetMode", e.target.value)}>
            <option value="power">Power</option>
            <option value="hr">Heart rate</option>
          </NativeSelect>
        </Label>
      </div>
      <p className="text-muted-foreground">
        {s.w_per_kg ? `${s.w_per_kg} W/kg. ` : ""}
        FTP source: {s.ftp_source ?? "manual"}
        {s.ftp_source_date ? ` (${s.ftp_source_date.slice(0, 10)})` : ""}
        {s.eftp ? `. intervals.icu estimates ${Math.round(s.eftp)} W.` : "."}
      </p>
      {problems.map((p) => (
        <p key={p}>{p}</p>
      ))}
      <Button size="sm" disabled={busy || !dirty || problems.length > 0} onClick={submit}>
        Save changes
      </Button>
      {error && <p role="alert">Couldn’t save: {error}</p>}
    </div>
  )
}

function Rider() {
  const [load, retry, refresh] = useLoad<SettingsRead>(getSettings)
  const [limits, setLimits] = useState<Limits>({})
  // After a save the server's answer replaces the loaded value in place, so the card never flashes back to "Loading…".
  const [now, setNow] = useState<{ s: SettingsRead; n: number } | null>(null)
  const [editing, setEditing] = useState<"power" | "hr" | null>(null)
  useEffect(() => { getLimits().then(setLimits, () => {}) }, [])
  const zonesSaved = () => { setEditing(null); setNow(null); refresh() }
  return (
    <Panel title="Rider" load={load} retry={retry}>
      {(loaded) => {
        const s = now?.s ?? loaded
        return (
          <div className="space-y-4">
            <RiderForm_ key={now?.n ?? 0} s={s} limits={limits} saved={(fresh) => setNow({ s: fresh, n: (now?.n ?? 0) + 1 })} />
            {now && <p role="status">Saved.</p>}
            <div className="grid gap-4 sm:grid-cols-2">
              {editing === "power" ? (
                <ZonesEditor kind="power" zones={s.power_zones} unit="W" onSaved={zonesSaved} onCancel={() => setEditing(null)} />
              ) : (
                <div className="space-y-2">
                  <Zones title="Power zones" zones={s.power_zones} unit="W" />
                  <Button size="sm" variant="outline" disabled={editing !== null} onClick={() => setEditing("power")}>
                    Edit power zones
                  </Button>
                </div>
              )}
              {editing === "hr" ? (
                <ZonesEditor kind="hr" zones={s.hr_zones} unit="bpm" onSaved={zonesSaved} onCancel={() => setEditing(null)} />
              ) : (
                <div className="space-y-2">
                  <Zones title="Heart-rate zones" zones={s.hr_zones} unit="bpm" />
                  <Button size="sm" variant="outline" disabled={editing !== null} onClick={() => setEditing("hr")}>
                    Edit heart-rate zones
                  </Button>
                </div>
              )}
            </div>
          </div>
        )
      }}
    </Panel>
  )
}

function Sync() {
  const [conn, retryConn] = useLoad<IcuConnection>(getIcuConnection)
  const [status, retryStatus] = useLoad<SyncStatus>(getSyncStatus)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [confirming, setConfirming] = useState(false)
  const disconnect = async () => {
    setBusy(true)
    setError("")
    try {
      await disconnectIcu()
      setConfirming(false)
      retryConn()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }
  const go = useCallback(async () => {
    setBusy(true)
    setError("")
    try {
      await syncNow()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
      retryStatus()
    }
  }, [retryStatus])
  return (
    <Panel title="intervals.icu" load={conn} retry={retryConn}>
      {(c) => (
        <div className="space-y-3 text-sm">
          <p>
            {c.connected ? `Connected${c.name ? ` as ${c.name}` : ""}${c.write_ok ? "" : ", read only"}.` : "Not connected."}
          </p>
          {c.needs_oauth_migration && c.oauth_available && <p>This connection uses an API key. Reconnect to switch to sign-in.</p>}
          {status.state === "ok" && (
            <p className="text-muted-foreground">
              {status.data.activity_records} rides and {status.data.wellness_records} wellness days stored
              {status.data.last_sync ? `. Last sync: ${String((status.data.last_sync as { timestamp?: string }).timestamp ?? "recorded")}.` : ". Never synced."}
              {status.data.auth_disabled ? " Background sync is paused: reconnect to resume." : ""}
            </p>
          )}
          {status.state === "error" && <p role="alert">Couldn’t read the sync state: {status.message}</p>}
          <div className="flex flex-wrap gap-2">
            <Button size="sm" disabled={busy || !c.connected} onClick={go}>
              {busy ? "Working…" : "Sync now"}
            </Button>
            {c.oauth_available && (
              <a href={connectUrl} className={buttonVariants({ size: "sm", variant: "outline" })}>
                {c.connected ? "Reconnect" : "Connect intervals.icu"}
              </a>
            )}
            {(!c.connected || c.method === "apikey") && <ApiKeyConnect onConnected={retryConn} />}
            {c.connected &&
              (confirming ? (
                <>
                  <Button size="sm" variant="destructive" disabled={busy} onClick={disconnect}>
                    Yes, disconnect
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setConfirming(false)}>
                    Stay connected
                  </Button>
                </>
              ) : (
                <Button size="sm" variant="ghost" onClick={() => setConfirming(true)}>
                  Disconnect…
                </Button>
              ))}
          </div>
          {error && <p role="alert">Couldn’t do that: {error}</p>}
        </div>
      )}
    </Panel>
  )
}

function About() {
  const [v] = useLoad<VersionInfo>(getVersion)
  const [update, setUpdate] = useState<UpdateCheck | null>(null)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const check = async () => {
    setBusy(true)
    setError("")
    try {
      setUpdate(await checkUpdate(true))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <Panel title="About" load={v} retry={() => location.reload()}>
      {(info) => (
        <div className="space-y-2 text-sm">
          <dl className="space-y-1">
            <Row label="Version" value={info.version} />
            <Row label="Data folder" value={<code className="break-all">{info.data_dir}</code>} />
          </dl>
          <Button size="sm" variant="outline" disabled={busy} onClick={check}>
            Check for updates
          </Button>
          {update && (
            <p role="status">
              {update.error
                ? `Couldn’t reach the release server: ${update.error}`
                : update.update_available
                  ? <>Version {update.latest} is available. {update.release_url && <a className="underline" href={update.release_url}>Release notes</a>}</>
                  : "You are on the latest version."}
            </p>
          )}
          {error && <p role="alert">Couldn’t check: {error}</p>}
        </div>
      )}
    </Panel>
  )
}

export function Settings() {
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2" aria-label="Settings">
      <p className="text-sm lg:col-span-2">New here, or want to check your setup? <a className="underline" href="#/onboarding">Run the guided setup</a>.</p>
      <div className="lg:col-span-2">
        <Rider />
      </div>
      <Appearance />
      <Sync />
      <AiCoachSettings />
      <NutritionSettings />
      <NotificationsSettings />
      <CalendarPush />
      <Folders />
      <FolderImport />
      <LocationCard />
      <About />
      <YourData />
      <div className="lg:col-span-2">
        <FtpHistory />
      </div>
      <div className="lg:col-span-2">
        <SportsCard />
      </div>
      <p className="text-sm lg:col-span-2">Bikes, shoes and components: <a className="underline" href="#/gear">Gear and service reminders</a>.</p>
      <div className="lg:col-span-2"><RunZones /></div>
      <div className="lg:col-span-2"><RacePredictor /></div>
      <div className="lg:col-span-2"><SwimZones /></div>
      <div className="lg:col-span-2"><SwimSessions /></div>
      <div className="lg:col-span-2">
        <Diagnostics />
      </div>
    </div>
  )
}
