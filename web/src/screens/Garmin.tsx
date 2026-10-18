import { useState } from "react"

import type { GarminStatus } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { garminDisconnect, garminLogin, garminMfa, garminRelay, garminSync, getGarmin } from "@/lib/settings"
import { Panel, useLoad } from "@/screens/panel"

/** Garmin Connect: the source of sleep, HRV, resting HR and activity files. */
export function Garmin() {
  const [load, retry, refresh] = useLoad<GarminStatus>(getGarmin)
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [code, setCode] = useState("")
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState("")
  const [error, setError] = useState("")
  const [confirming, setConfirming] = useState(false)
  const run = async (work: () => Promise<string>) => {
    setBusy(true)
    setError("")
    setMsg("")
    try {
      setMsg(await work())
      refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <Panel title="Garmin Connect" load={load} retry={retry}>
      {(g) => {
        if (!g.available) return <p className="text-sm text-muted-foreground">Garmin support is not installed in this build.</p>
        const signIn = !g.connected || g.needs_login
        return (
          <div className="space-y-3 text-sm">
            <p>
              {g.connected && !g.needs_login ? `Connected${g.name ? ` as ${g.name}` : ""}.` : g.needs_login ? "Garmin no longer accepts the saved sign-in. Sign in again." : "Garmin is not connected."}
            </p>
            {g.connected && (
              <p className="text-muted-foreground">
                {g.last_sync_at
                  ? `Last sync: ${new Date(g.last_sync_at).toLocaleString()}. ${g.health_days} days of health data in it; ${g.activities_imported} activities imported so far.`
                  : "Not synced yet."}
              </p>
            )}
            {g.last_error && !g.needs_login && <p role="alert">Last sync failed: {g.last_error}</p>}
            {signIn && !g.mfa_pending && (
              <div className="space-y-2">
                <p className="text-muted-foreground">
                  Sign in with your Garmin account. Only the sign-in tokens Garmin issues are kept on this computer, never your password. Sleep, HRV and resting HR from Garmin replace the values intervals.icu has.
                </p>
                <div className="flex flex-wrap items-end gap-2">
                  <Label className="flex-col items-start gap-1">
                    Email
                    <Input className="w-56" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} />
                  </Label>
                  <Label className="flex-col items-start gap-1">
                    Password
                    <Input className="w-48" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
                  </Label>
                  <Button
                    size="sm"
                    disabled={busy || !email.trim() || !password}
                    onClick={() =>
                      run(async () => {
                        const r = await garminLogin(email, password)
                        setPassword("")
                        return r.mfa_pending ? "Garmin sent you a code. Enter it below." : "Connected. The first sync runs within the hour, or press Sync Garmin now."
                      })
                    }
                  >
                    {busy ? "Signing in…" : "Sign in"}
                  </Button>
                </div>
              </div>
            )}
            {g.mfa_pending && (
              <div className="flex flex-wrap items-end gap-2">
                <Label className="flex-col items-start gap-1">
                  Code from Garmin
                  <Input className="w-32" inputMode="numeric" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value)} />
                </Label>
                <Button
                  size="sm"
                  disabled={busy || !code.trim()}
                  onClick={() =>
                    run(async () => {
                      await garminMfa(code)
                      setCode("")
                      return "Connected."
                    })
                  }
                >
                  Verify
                </Button>
              </div>
            )}
            {g.connected && !g.needs_login && (
              <>
                <Label className="items-start gap-2 font-normal">
                  <Checkbox checked={g.relay_to_icu} disabled={busy} onCheckedChange={(on) => run(async () => ((await garminRelay(on === true)).relay_to_icu ? "New Garmin activities will be sent to intervals.icu." : "Stopped sending activities to intervals.icu."))} />
                  <span>Send new Garmin activities to intervals.icu. Turn this on only if intervals.icu no longer gets them from Garmin itself, or rides will be doubled.</span>
                </Label>
                <div className="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    disabled={busy}
                    onClick={() =>
                      run(async () => {
                        const r = await garminSync()
                        return r.skipped === "busy" ? "A sync is already running." : `Synced ${r.health_days} days of health data and ${r.activities_imported} new activities.`
                      })
                    }
                  >
                    {busy ? "Working…" : "Sync Garmin now"}
                  </Button>
                  {confirming ? (
                    <>
                      <Button size="sm" variant="destructive" disabled={busy} onClick={() =>
                          run(async () => {
                            await garminDisconnect()
                            setConfirming(false)
                            return "Disconnected. Data already synced stays."
                          })
                        }
                      >
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
                  )}
                </div>
              </>
            )}
            {msg && <p role="status">{msg}</p>}
            {error && <p role="alert">Couldn’t do that: {error}</p>}
            <p className="text-xs text-muted-foreground">Garmin has no public API for personal apps; this uses the same service as Garmin’s own app, so a change on Garmin’s side can stop it working until an update.</p>
          </div>
        )
      }}
    </Panel>
  )
}
