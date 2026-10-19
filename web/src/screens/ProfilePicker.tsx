import { useCallback, useEffect, useState } from "react"
import { SettingsIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  PALETTE,
  deleteProfile,
  initials,
  listProfiles,
  safeColor,
  switchProfile,
  updateProfile,
  type Profile,
} from "@/lib/profiles"

const goHome = () => window.location.assign("/")

export function ProfilePicker({ onSwitched = goHome }: { onSwitched?: () => void }) {
  const [profiles, setProfiles] = useState<Profile[] | null>(null)
  const [skipPicker, setSkipPicker] = useState(false)
  const [editing, setEditing] = useState<Profile | null>(null)
  const [error, setError] = useState("")

  const load = useCallback(() => {
    listProfiles()
      .then(setProfiles)
      .catch((e: Error) => setError(e.message))
  }, [])
  useEffect(load, [load])

  const pick = (p: Profile) =>
    switchProfile(p.id, skipPicker)
      .then(onSwitched)
      .catch((e: Error) => setError(e.message))

  if (profiles === null) {
    return <Shell subtitle="">{error && <p role="alert" className="text-destructive">{error}</p>}</Shell>
  }

  if (profiles.length === 0) {
    return (
      <Shell subtitle="No profiles yet">
        <Card>
          <CardContent className="flex flex-col items-center gap-3 p-8">
            <h2 className="text-lg font-semibold">Create your first profile</h2>
            <p className="max-w-sm text-sm text-muted-foreground">
              Every rider needs a profile. It holds your FTP, weight, training plans, ride history
              and intervals.icu connection.
            </p>
            <Button render={<a href="#/profile-setup" />}>Create account to start</Button>
          </CardContent>
        </Card>
      </Shell>
    )
  }

  return (
    <Shell subtitle="Who's riding today?">
      {error && <p role="alert" className="mb-4 text-sm text-destructive">{error}</p>}
      <div className="grid grid-cols-[repeat(auto-fit,minmax(180px,220px))] justify-center gap-4">
        {profiles.map((p) => (
          <Card key={p.id} className="relative">
            <button
              type="button"
              className="absolute inset-0 rounded-[inherit] focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
              aria-label={`Ride as ${p.name}`}
              onClick={() => pick(p)}
            />
            <CardContent className="flex flex-col items-center gap-1 p-6">
              <div
                className="mb-2 flex size-14 items-center justify-center rounded-full bg-primary text-xl font-bold text-primary-foreground"
                style={safeColor(p.color) ? { background: safeColor(p.color) } : undefined}
              >
                {initials(p.name)}
              </div>
              <div className="font-semibold">{p.name}</div>
              <div className="text-xs text-muted-foreground">
                {[p.ftp ? `${p.ftp}W` : "", p.weight_kg ? `${p.weight_kg}kg` : ""].filter(Boolean).join(" ")}
              </div>
            </CardContent>
            <Button
              variant="ghost"
              size="icon"
              className="absolute top-1.5 right-1.5"
              aria-label={`Settings for ${p.name}`}
              onClick={() => setEditing(p)}
            >
              <SettingsIcon />
            </Button>
          </Card>
        ))}
        <Card className="border-dashed">
          <CardContent className="flex h-full items-center justify-center p-6">
            <Button variant="ghost" className="max-md:min-h-11" render={<a href="#/profile-setup" />}>
              + Add Profile
            </Button>
          </CardContent>
        </Card>
      </div>
      <div className="mt-6 flex items-center justify-center gap-2">
        <Checkbox
          id="skip-picker"
          checked={skipPicker}
          onCheckedChange={(v) => setSkipPicker(v === true)}
        />
        <Label htmlFor="skip-picker">Remember my choice</Label>
      </div>
      {editing && (
        <ProfileSettings
          key={editing.id}
          profile={editing}
          onClose={() => setEditing(null)}
          onChanged={() => {
            setEditing(null)
            load()
          }}
        />
      )}
    </Shell>
  )
}

function Shell({ subtitle, children }: { subtitle: string; children: React.ReactNode }) {
  return (
    <div className="mx-auto flex min-h-svh max-w-2xl flex-col justify-center px-6 py-10 text-center">
      <h1 className="text-3xl font-semibold tracking-tight">Shepherd</h1>
      <p className="mb-8 text-muted-foreground">{subtitle}</p>
      {children}
    </div>
  )
}

function ProfileSettings({
  profile,
  onClose,
  onChanged,
}: {
  profile: Profile
  onClose: () => void
  onChanged: () => void
}) {
  const [name, setName] = useState(profile.name)
  const [color, setColor] = useState((safeColor(profile.color) || PALETTE[0]).toLowerCase())
  const [confirm, setConfirm] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")

  const run = (action: () => Promise<unknown>, label: string) => {
    setBusy(true)
    setError("")
    action()
      .then(onChanged)
      .catch((e: Error) => setError(`${label} failed: ${e.message}`))
      .finally(() => setBusy(false))
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Profile settings</DialogTitle>
          <DialogDescription>
            Editing "{profile.name}" ({profile.id})
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 text-left">
          <div className="grid gap-2">
            <Label htmlFor="pp-name">Name</Label>
            <Input id="pp-name" maxLength={64} value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="grid gap-2">
            <Label>Profile color</Label>
            <div className="flex flex-wrap gap-2">
              {PALETTE.map((c) => (
                <button
                  key={c}
                  type="button"
                  aria-label={`Color ${c}`}
                  aria-pressed={c === color}
                  className="size-7 rounded-full ring-offset-2 ring-offset-background aria-pressed:ring-2 aria-pressed:ring-foreground"
                  style={{ background: c }}
                  onClick={() => setColor(c)}
                />
              ))}
            </div>
          </div>
          <div className="grid gap-2 border-t pt-4">
            <h3 className="font-semibold text-destructive">Danger zone</h3>
            <p className="text-xs text-muted-foreground">
              Deleting this profile permanently removes its rides, plans, nutrition products,
              intervals.icu credentials and database. This cannot be undone.
            </p>
            <Label htmlFor="pp-confirm">Type DELETE to enable deletion</Label>
            <Input id="pp-confirm" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
            <Button
              variant="destructive"
              disabled={busy || confirm !== "DELETE"}
              onClick={() => run(() => deleteProfile(profile.id), "Delete")}
            >
              Delete account
            </Button>
          </div>
          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button
            disabled={busy || !name.trim()}
            onClick={() => run(() => updateProfile(profile.id, name.trim(), color), "Save")}
          >
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
