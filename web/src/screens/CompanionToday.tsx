import { companionLabel, getCompanions, NOT_VALIDATED } from "@/lib/companions"
import { fmtMinutes } from "@/lib/home"
import { useLoad } from "@/screens/panel"

const thisWeek = () => getCompanions()

/** Today's run, swim or strength session for Home's "At a glance". Renders nothing when there is none. */
export function CompanionToday() {
  const [load] = useLoad(thisWeek)
  if (load.state !== "ok") return null
  const list = Array.isArray(load.data.today) ? load.data.today : []
  if (!list.length) return null
  return (
    <div aria-label="Other sports today" className="mt-2 space-y-1">
      <ul className="space-y-1">
        {list.map((c) => (
          <li key={c.id} className="text-sm">
            <span className="font-medium">{companionLabel(c)}</span> · {fmtMinutes(c.duration_min ?? 0)}
            {c.status === "done" ? " · done" : ""}
            <span className="block text-xs text-muted-foreground">{c.description}</span>
          </li>
        ))}
      </ul>
      <p className="text-xs text-muted-foreground">{load.data.note || NOT_VALIDATED}</p>
    </div>
  )
}
