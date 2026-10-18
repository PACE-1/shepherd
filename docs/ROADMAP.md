# Roadmap (working plan, 2026-10-17)

Source of truth for scope is the GitHub board and milestones; this file orders them and records dependencies.

## Rules for every item
- One branch and PR per issue (or per tight group). Local gate (`tools/gate.sh`) green before merge.
- Tests with the change: a failing test first for bugs, contract tests for new endpoints, vitest for new screens, one browser test per new screen.
- API changes: Pydantic response model, regenerate `tests/api_contract.json` and `web/src/api/schema.d.ts`.
- Running and swim numbers need a source: a named published method, reference values from it as tests, and a stated confidence. No invented coefficients.
- Planner output changes (#11, #24, #111, #113, #125) go up for review rather than straight to merge.

## Wave 0: reliability (milestone "Shepherd reliability")
| Issue | What | Notes |
|---|---|---|
| #140 | AI key carried to another provider | security, first |
| #141 | AI calls block the event loop | thread pool |
| #142 | Check-in edit deletes notes | server keeps stored notes |
| #143 | Missing ride returns 500 | return the 404 |
| #144 | Summary image downloads | open inline in a tab |
| #139 | Zwift upload errors | intervals.icu setting, not ours; hint added in Settings |
| #107 | CI mostly red | lint errors, Playwright smoke in CI |

## Wave 1: foundation and everyday experience
| Issue | What | Depends on |
|---|---|---|
| #109 | Multi-sport data model (sport on activities, per-sport thresholds, per-sport and combined load) | none; everything in waves 3 and 4 needs it |
| #145 | At-a-glance home for newer riders | none |
| #106 | Theme options | none |
| #105 | Guided onboarding | #145 helps |
| #130 | Mobile layout and installable web app | #145 |

## Wave 2: tools that work for every sport
| Issue | What | Depends on |
|---|---|---|
| #110 | Workout builder, push to Garmin through intervals.icu | #109 for run and swim targets; cycling part can ship first |
| #113 | Injury and illness, return ramp, ramp-rate warning | #109 |
| #111 | Race planner: A/B/C, taper, race-day plan | #109, #113 |
| #114 | Weight trend, W/kg history, power-duration model | none |
| #116 | Ride comparison | none |
| #129 | Data export and restore | none |
| #131 | Notifications | none |
| #127 | Strength and mobility sessions | planner |

## Wave 3: running and triathlon
Order: #118 zones, #119 load, #128 readiness across sports, #120 run workouts, #121 race predictor, #122 swim, #124 sport balance, #123 bricks, #125 race-distance plans, #126 open-water notes. All depend on #109.

## Wave 4: needs a decision or an outside system
- #112 fueling: pick a self-hosted tracker with a phone app and an API first; then integrate.
- #115 gear, #117 weather: integrations; weather needs a source and a location setting.
- #13 server exposure, #31 Garmin data via intervals.icu, #132 rest of the rebrand (detach fork, domain, trademark): external or owner decisions.
- #94, #9, #10, #11, #23, #24, #26, #16: maintenance and refactors from the earlier roadmap; planner ones need review.

## What "done" means for the large items
A vertical slice that works end to end and is tested, with the remaining scope written on the issue, beats a wide unfinished layer. Each issue is closed only when its own checklist is met.

## Status (2026-10-18) and known gaps

Everything below is on branch `claude/peaceful-bell-wcwgkb`, not yet on `clean-main`. No issue is closed: each closes only when its own checklist is met. "Verified" means unit/contract/browser tests passed in a container with no real riders' data and no live external services.

| Issue | State | Remaining scope (known gaps) |
|---|---|---|
| #107 CI | done locally | Not yet seen green on GitHub Actions. |
| #109 multi-sport model | slice | Per-sport detail pages and zone-aware charts; plan data is still cycling-only (`PlannedSession` has no sport field). |
| #110 workout builder | cycling only | Run and swim targets; `.fit` export; duplicate/delete; Edit link on Library rows. |
| #111 race planner | slice | Run/swim races; segment pacing; fueling in the race-day plan (comes from #112); nav link to `#/races`. B races now taper (7 days at 60%): changes plans of riders who already have B races, needs review. |
| #112 fueling | slice | SparkyFitness endpoints verified from its source, never run against a live server. On-demand sync only (no background sync); no targets pushed back; https with self-signed certificates fails. |
| #113 injury/illness | slice | Needs review: any episode gets at least 3 weeks of easy-only return, which conflicts with `SCIENCE.md` 1b for short illnesses. Nothing rebuilds the plan when an episode's end date passes; only the cycling plan pauses; no nav link to `#/injury`. |
| #114/#116 analytics | slice | W/kg for 5- and 20-minute power over time; cadence/speed/elevation/zone comparison; runs. |
| #117 weather | slice | Every non-rest session counts as outdoor (plans have no indoor flag); the whole riding day is rated (sessions have no time of day); thresholds are heuristic defaults; extra-rider wizard has no location step. |
| #118/#119 run | slice | Run pace/gradient streams are not stored, so rTSS uses average pace (low on hilly or interval runs); grade adjustment only in the converter; nothing checked against real recorded runs; cadence only, no ground-contact time. |
| #121 race predictor | slice | "What fitness change reaches a target time"; checking predictions against real race results; the card does not refresh after a critical-speed save until Settings reloads. |
| #122/#126 swim | slice | No swim pace zones (no citable exact percentages); sTSS uses average speed (low to moderate confidence); no stroke count or SWOLF in intervals.icu data; open-water notes are not surfaced in race-week planning (needs the planner). |
| #128 readiness | slice | Sleep trends and illness warning signs; runs/swims without an intervals.icu load count as zero. |
| #129 export | slice | Restore is a stop-the-app command (`python -m backup restore`), not in the UI. |
| #131 notifications | slice | No web-push or email; no per-event channel choice; failed ntfy posts are not retried. |

Known defects found, not fixed:
- One ride-detail load parses the same FIT file four times (stats, device info, RR intervals, sport), about 1 s each even for a 5-minute file; Compare loads two rides. Eight parse sites, and existing tests patch the parser, so a shared cache needs care.
- `web/src/lib/planForm.ts` sends the A event inside `events` when an event goal has B/C races; `generate_plan` refuses an A there with a 400.
- Test-order pollution: running `test_api_contract.py` before the account tests in one process fails about 17 of them (they pass alone). The full parallel gate is unaffected.
- Not started (need a design decision): #123 bricks, #125 race-distance plans, #127 strength sessions, run/swim sessions in the plan. They depend on how a plan holds non-cycling sessions.
