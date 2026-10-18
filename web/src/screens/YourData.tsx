import { Card, CardContent } from "@/components/ui/card"

const FILES = [
  { href: "/api/export/activities.csv", label: "Activities (CSV)" },
  { href: "/api/export/wellness.csv", label: "Wellness: fitness, HRV, sleep (CSV)" },
  { href: "/api/export/checkins.csv", label: "Daily check-ins (CSV)" },
  { href: "/api/export/backup", label: "Full backup (.tar.gz)" },
]

/** Open-file downloads of the rider's data, and how to restore a backup. */
export function YourData() {
  return (
    <Card>
      <CardContent className="space-y-3 p-4 text-sm">
        <h2 className="text-sm font-semibold">Your data</h2>
        <p className="text-muted-foreground">CSV files open in any spreadsheet. The full backup holds every profile, plan, ride file and database.</p>
        <ul className="list-disc space-y-1 pl-5">
          {FILES.map((f) => (
            <li key={f.href}><a className="underline" href={f.href} download>{f.label}</a></li>
          ))}
        </ul>
        <p className="text-muted-foreground">
          The backup leaves out your intervals.icu and AI keys, so enter them again after a restore. To restore, stop Shepherd and run{" "}
          <code>python -m backup restore backup.tar.gz</code> (in Docker, the same command inside the container with <code>--home /data</code>).
        </p>
      </CardContent>
    </Card>
  )
}
