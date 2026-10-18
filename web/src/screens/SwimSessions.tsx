import type { SwimSessions as SwimSessionsData } from "@/api/types"
import { per100 } from "@/lib/swim"
import { getSwimSessions, rangeLabel, sessionTextUrl } from "@/lib/swimSessions"
import { Panel, useLoad } from "@/screens/panel"

function Sessions({ data }: { data: SwimSessionsData }) {
  return (
    <div className="space-y-3 text-sm">
      <p>
        {data.css_s_per_100m ? `Sets are written for your CSS, ${per100(data.css_s_per_100m)}.` : "No swim CSS yet, so sets show metres and an effort, without times. Save a CSS test above to get a time for every repeat."}{" "}
        {data.pool_m} m pool assumed.
      </p>
      <ul className="space-y-3">
        {data.sessions?.map((s) => (
          <li key={s.id} className="space-y-1 border-t pt-3 first:border-t-0 first:pt-0">
            <p className="font-medium">
              {s.name} <span className="font-normal text-muted-foreground">· {s.hard ? "hard" : "easy"} · {s.minutes} min (range {rangeLabel(s.minutes_min, s.minutes_max)})</span>
            </p>
            <p className="text-muted-foreground">{s.intent}</p>
            <ul className="list-disc pl-5" aria-label={`${s.name} sets`}>
              {s.lines?.map((ln) => <li key={ln}>{ln}</li>)}
            </ul>
            <a className="underline" href={sessionTextUrl(s.id)} download aria-label={`Download ${s.name} as text`}>Download as text</a>
          </li>
        ))}
      </ul>
      <p className="text-xs text-muted-foreground">{data.download_note} {data.source} {data.not_validated}</p>
    </div>
  )
}

/** The swim session templates with their sets for the rider's CSS (sessions_swim.py). */
export function SwimSessions() {
  const [load, retry] = useLoad<SwimSessionsData>(getSwimSessions)
  return <Panel title="Swim sessions" load={load} retry={retry}>{(d) => <Sessions data={d} />}</Panel>
}
