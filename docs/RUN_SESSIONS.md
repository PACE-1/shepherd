# Run sessions (#120)

**Design templates after Daniels; not validated against recorded runs.** Nothing here has been checked
against real runs, and the `.fit` files have not been tried on a real Garmin device.

Code: `src/sessions_run.py` (templates), `src/routes_run_sessions.py` (API and downloads),
`web/src/screens/RunWorkouts.tsx` (the "Run workouts" panel at the top of the Library).

## Sources

- **Structure:** Jack Daniels, *Daniels' Running Formula*, 3rd ed. (Human Kinetics, 2014), and its
  intensity categories E (easy), M (marathon), T (threshold), I (interval) and R (repetition). The figures
  below are Daniels' stated guidelines as used here. Items marked *verify* should be checked against the book.
- **Targets:** Joe Friel's run pace zones as % of threshold pace (`run_metrics.FRIEL_PACE`, reused).
- **Load:** TrainingPeaks rTSS (`run_metrics.rtss`) at each step's intended zone. This is an **estimate**,
  not a measured load.

## Templates

| id | Daniels | Stimulus | Hard | Minutes | Structure |
|---|---|---|---|---|---|
| run-easy | E | aerobic | no | 30-60 | continuous E (Friel Z2) |
| run-long | E (L) | aerobic | no | 60-150 | continuous E; Daniels' 2.5 h cap |
| run-recovery | E | recovery | no | 20-40 | very easy jog (Z1) |
| run-strides | R | speed | no | 30-50 | E running, then 6 x 20 s strides, 1 min jog (*verify* count and rest) |
| run-tempo | T | threshold | yes | 40-60 | 20 min continuous T (Z4) |
| run-cruise | T | threshold | yes | 45-70 | 2-4 x 10 min T, 2 min easy (1 min per 5 min, *verify*) |
| run-intervals | I | vo2max | yes | 45-60 | 3-5 x 4 min I (Z5b), equal-time jog |
| run-hills | I | vo2max | yes | 45-60 | 4-6 x 3 min uphill by I effort, jog down (*verify*: Shepherd runs I reps on a hill) |

Daniels' guidelines used: a tempo run of about 20 minutes; cruise intervals of about 5-15 minutes with
short rests; I reps of about 3-5 minutes with a jog recovery of equal or slightly shorter time; strides of
about 20-30 seconds; a long run of at most the lesser of about 25 % of weekly running and 150 minutes.

**Long-run cap:** only the 150-minute (2.5 h) cap is implemented, as the template's longest length. The
25 % share (*verify*) is not enforced: a template does not know the week's running total.

Shepherd's own choices (not from Daniels): placing Daniels' categories in Friel's zones (recovery jog Z1,
E/L Z2, T Z4, I Z5b, R Z5c) (*verify*); at least 10 minutes of easy warm-up and cool-down around hard work;
rep lengths inside Daniels' ranges; rep counts; and the minute ranges in the table.

## Targets

- With a saved run threshold pace, each step has a `pace_pct_threshold` target. `lo` is the fast end and
  `hi` the slow end, as % of threshold pace (time per km), plus the s/km values they give. Friel's open
  zones keep one end open: Z1 has no slow bound and Z5c no fast bound.
- Without one, each step has an `effort` label (e.g. "comfortably hard"). No pace is invented.
- Hill repeats always use effort, because a pace target means little uphill.
- Heart-rate targets are not offered yet.

`workout_builder.validate(workout, workout_builder.RUN_TARGETS)` validates both kinds. The default
(cycling) validation still rejects them.

## Load estimate

IF = threshold pace / pace = 100 / zone %, so the estimate needs no saved threshold. A zone counts at the
middle of its bounds. An open zone counts at its one published bound: Z1 at 129 %, which overstates a jog,
and Z5c at 90 %, which understates strides.

## API

- `GET /api/run/sessions?type=&min_minutes=&max_minutes=&max_rtss=`: the filtered library. `type`
  matches the kind, the stimulus or the Daniels letter. Each row's workout is built for the rider's current
  thresholds, at a length inside both its own range and the filter's.
- `GET /api/run/sessions/{id}?minutes=`: one session at a chosen length.
- `GET /api/run/sessions/{id}/download?minutes=&format=fit|txt`: the session as a file.
  - `.fit` is a FIT workout file with sport *running*, built with `fit_tool` like the cycling export.
    Pace targets become a custom speed range in m/s. Effort steps and open zones become open steps named
    with their cue. Reps use a repeat-until-steps-complete step.
  - `.txt` is the same workout as plain text, for any watch or app.

## Planner

The companion planner (`multisport_plan.overlay`) loads this library automatically and places its
templates. It also retires `placeholder-run-easy`.
