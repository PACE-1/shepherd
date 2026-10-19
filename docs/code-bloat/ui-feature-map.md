# Workflow map: legacy dashboard to the TypeScript UI (roadmap #3, #25)

One row per workflow. "New UI" is under `web/src`. The legacy dashboard
(`src/templates/dashboard.html`, the setup and profile pages and `src/static`)
was deleted in 1.0.1; this table records where each workflow went.

## Seams the new UI shares

| Concern | Owner | Notes |
|---|---|---|
| Routing | `App.tsx`, hash routes (`#/home`, `#/plan`, …) | One tab per route; `AppShell` renders the section nav and the active profile id. |
| HTTP and errors | `lib/api.ts` (`api`, `apiFull`) | JSON in and out; any non-2xx throws `ApiError` carrying the server's `error` or `detail` text. `apiFull` also returns headers. |
| Loading, empty, failure | `screens/panel.tsx` (`useLoad`, `Panel`) and per-screen state | Every read shows Loading, then data, an empty sentence, or an alert with Retry. A failing card never blanks its neighbours. |
| Response types | `api/schema.d.ts`, generated from `tests/api_contract.json` | `tools/gen-api-types.sh`. `tests/test_api_contract.py` fails when a model drifts. See `docs/API.md`. |
| State | React state per screen; per-profile `localStorage` keys through `useShell().lsKey` | No module-level globals, no document-wide IDs, no polling timers. |
| Maintenance that ran on tab open | the server (`_after_background_sync`, `_maybe_auto_reforecast`) | The weekly recalc runs once a day from the sync loop; reforecast runs after ride sync. |

## Workflows

| Workflow | New UI | Main endpoints | Tests | Legacy behaviour not yet in the new UI (from the route list, not an exhaustive audit) |
|---|---|---|---|---|
| First-run setup | `Setup.tsx` | `/api/setup/*`, `/api/icu/connection` | vitest, e2e | none |
| Profiles | `ProfilePicker.tsx`, `ProfileSetup.tsx` | `/api/profiles*` | vitest, e2e | none |
| Home | `Home.tsx`, `Readiness.tsx`, `DailyCheckIn.tsx`, `Hrv.tsx`, `BodyPerf.tsx`, `Records.tsx`, `RetestNudge.tsx`, `WeekSummary.tsx`, `DfaSnapshot.tsx` | `/api/plan`, `/api/rider-stats`, `/api/programme/summary`, `/api/readiness*`, `/api/today-session*`, `/api/daily-log`, `/api/wellness/*`, `/api/metrics/*`, `/api/week-summary` | vitest, e2e | none |
| Plan | `Plan.tsx`, `PlanGenerate` (+`PlanAdvanced`), `PlanCalendar`, `PlanTimeOff`, `PlanRace`, `PlanAvailability`, `PlanRematch`, `PlanRedraw`, `SessionExport`, `GoalEvent` | `/api/plan*`, `/api/calendar`, `/api/icu/races` | vitest, e2e | the small power-block pictures on completed days of the legacy grid (`/api/activities/blocks`): the new calendar links each ridden day to its ride instead |
| Workout Library | `Library.tsx`, `WorkoutCard.tsx` | `/api/workouts*`, `/api/workout/*`, `/api/download/zwo/*`, `/api/export/fit-workout`, `/api/surface-types` | vitest, e2e | the mini power profile in each list row (`/api/workouts/bulk-segments`, endpoint removed): the profile shows when a workout is opened |
| Workout Shuffle | `Shuffle.tsx` | `/api/picker` | vitest, e2e | none |
| Analysis | `Analysis.tsx`, `Chart.tsx`, `RideDetail.tsx`, `RideTools.tsx`, `EnergySystems.tsx`, `TrainingModels.tsx`, `HistoryBackfill.tsx` | `/api/wellness`, `/api/profile/*`, `/api/rides*`, `/api/ride/*`, `/api/activity/*/race` | vitest, e2e | none |
| Settings | `Settings.tsx`, `ZonesEditor.tsx`, `Folders.tsx`, `CalendarPush.tsx`, `Diagnostics.tsx`, `FtpHistory.tsx` | `/api/settings*`, `/api/icu/*`, `/api/sync*`, `/api/version`, `/api/update/check`, `/api/logs`, `/api/diag/*` | vitest, e2e | none |
| DFA α1 | `Dfa.tsx` | `/api/profile/dfa-*` | vitest, e2e | none |

## Retirement

The legacy dashboard was removed once every row above had no legacy-only behaviour (1.0.1, roadmap #25). `/`, `/setup`, `/profile-picker` and `/profile-setup` now redirect into the web app under `/v2`. The power-block pictures and per-row library profiles in the last column are the only things not carried over.
