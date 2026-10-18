# Swim sessions

The swim session library for the multi-sport plan (follow-on to #122). Code: `src/sessions_swim.py`
(templates), `src/routes_swim_sessions.py` (`GET /api/swim/sessions`, `GET /api/swim/sessions/{id}/text`),
`web/src/screens/SwimSessions.tsx` (a card under the swim CSS area in Settings).

**Not validated.** The set shapes are common coaching practice templates, not a validated protocol, and
nothing here has been checked against real recorded swims. The screen, the download and the plan say so.

## Pace: the rider's own CSS, nothing else

* CSS is the rider's saved `swim_css` (s/100 m), from a 400 m / 200 m test (Wakayoshi et al. 1992, Eur J
  Appl Physiol 64:153-157; simple two-swim method 1993, Int J Sports Med 14(7):368-372; see
  `src/swim_metrics.py`).
* "At CSS" means the CSS pace itself. There are **no percentage zones**: none could be cited
  (`swim_metrics.ZONES_NOTE`, ROADMAP).
* Easy swimming has no pace. It carries the effort label "easy, relaxed" and is written in minutes.
* Sets are written in metres, rests in seconds. With a saved CSS each repeat becomes seconds
  (`distance x CSS / 100`), and the number of repeats is fitted to the session length so the workout lasts
  exactly the minutes the planner asked for (spare seconds go to warm-up and cool-down). Without a CSS
  the set stays in metres under the effort label "comfortably hard, steady (CSS effort)", the repeat count
  runs across the template's minute range, and the workout's note says times need a CSS.
* Warm-up 25 % and cool-down 15 % of the session, the rests and the repeat caps are design choices of this
  library, with no published dose-response behind them.
* Pool: 25 m assumed (every distance is a whole number of 25 m lengths). Open-water pacing is not given.

## Templates

| id | kind | planner type | hard | minutes | shape |
| --- | --- | --- | --- | --- | --- |
| `swim-easy-technique` | easy | swim_endurance | no | 30-60 | warm-up, technique block, continuous easy, cool-down; all "easy, relaxed" |
| `swim-recovery` | recovery | swim_endurance | no | 20-40 | continuous easy, loose |
| `swim-css-endurance` | endurance | swim_endurance | yes | 40-70 | up to 6 x 400 m at CSS, 30 s rest (or the same metres as one continuous swim at CSS) |
| `swim-css-intervals` | css | swim_css | yes | 40-70 | up to 20 x 100 m (15 s rest) up to 50 min, 200 m (20 s rest) beyond |
| `swim-threshold-plus` | threshold | swim_css | yes | 35-55 | up to 24 x 50 m at CSS or faster, 15 s rest; the repeat time is the CSS-pace ceiling |

Hard templates count against the engine's hard-day budget (`multisport_plan.overlay`); easy ones fill the
rest of the swim hours. `placeholder-swim-easy` is unregistered.

## Workout shape

`builder(thresholds, minutes)` returns `{"name", "description", "steps", "note"}` in the
`src/workout_builder.py` step shape: `warmup` / `work` / `cooldown` steps and one `repeat`
(`count`, `on`, `off`). Targets: `{"kind": "css", "pace_s_per_100m": s, "label": "at CSS" | "at CSS or faster"}`
(only when a CSS is saved) and `{"kind": "effort", "label": ...}`. `workout_builder.validate` does not know
these two kinds yet (it accepts power and heart rate only); the plan route returns the workout as it is, and
nothing calls `validate` or `to_zwo` on a swim.

## Download

`GET /api/swim/sessions/{id}/text` is a plain-text attachment (`<id>.txt`). **No FIT or watch file is made
for swims.**
