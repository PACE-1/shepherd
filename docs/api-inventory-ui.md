# API inventory for the routes the web app calls (roadmap #10)

Scope: every `/api` route that `web/src` (screens and `lib/`) calls, found by
scanning for `/api/` string literals and matching them to the live OpenAPI
route table (method taken from the call's `method:` option, GET by default).
Seven routes are built through helpers (`one(id)`, `note(id)`, `episode(id)`)
and are added by hand; the rest come from the scan. `tests/test_api_ui_inventory.py`
repeats the scan on every run, so a new UI route without a model fails there.

Measured 2026-10-18 on the `worktree-agent-a41509ada31368585` branch:

| | before this slice | after |
|---|---|---|
| UI-called routes | 164 | 164 |
| with a response model | 146 | 156 |
| without one | 18 | 8 |

The 8 that remain have no JSON body to model (file downloads, an image, one
`204`); each carries its reason in `EXEMPT` in the test. The 10 added are
`GET /api/setup/limits`, `POST /api/setup/test-icu`, `POST /api/setup/check-activities`,
`GET /api/setup/pick-folder`, `POST /api/setup/save`, `GET /api/icu/athlete-numbers`,
`POST /api/sync`, `DELETE /api/rides/{ride_id}`, `POST /api/profile/dfa-backfill/cancel`
and `POST /api/diag/frontend-error`. Models document the response and never validate
it (`responses={200: {"model": ...}}`, see `src/api_models.py`).

"Kind" is the HTTP method class: GET is a read, every other method is a command.
A read here means the HTTP verb, not a promise of no side effects; the plan
commands and their locking are in `docs/code-bloat/api-inventory-home-plan.md`.

## Error and status shapes (as they are today)

Only documented here, nothing was changed. Counts are call sites at this commit.

| Shape | Where | Count / status codes |
|---|---|---|
| `{"error": "<sentence>"}` | `JSONResponse({"error": ...}, status)` in `app.py`, plus 3 in `routes_analytics.py` and 4 in `routes_builder.py` | 139 in `app.py`: 404 (48), 400 (40), 500 (29), 403 (4, `local-only`), 503 (2), 401 (1), 409 (1) |
| `{"detail": "<sentence>"}` | `raise HTTPException(status, detail)` (FastAPI default body) | 68 in `app.py`; the other `routes_*.py` files use only this form |
| `{"error": "Internal server error", "detail": "see server logs"}` | the global `Exception` handler, any unhandled error | 500; carries both keys, never the exception text |
| `{"detail": [{"type", "loc", "msg", "input"}]}` | FastAPI request validation (missing or mistyped query or body field) | 422; `detail` is a list, so `lib/api.ts` (`body.error ?? body.detail`) gets a list instead of a sentence |
| `200` with `{"ok": false, "error": "<sentence>"}` | setup probes `/api/setup/test-icu` and `/api/setup/check-activities`, and others (20 `"ok": False, "error"` sites in `app.py`) | HTTP success, failure in the body; the UI branches on `ok` |
| `204`, no body | `POST /api/activity/{id}/race` on success | its errors are `{"error"}` with 400, 404 or 500 |

Seen while probing the routes behind the new models: `POST /api/setup/save` with an
out-of-range value is `400 {"detail": "ftp=9999.0 out of range [50,600]"}`;
`POST /api/profile/dfa-backfill/cancel` with an unknown task is `404 {"error": "unknown task_id"}`
and without `task_id` is the 422 list form; `DELETE /api/rides/{id}` for a missing ride is
`404 {"error": "Ride not found"}`.

For a later decision (not done here): the UI copes with both sentence shapes
because `lib/api.ts` reads `error` then `detail`, but the 422 list form is not a
sentence, and the same kind of refusal is `error` in one route and `detail` in
another. Converging on one shape changes behaviour and belongs in its own slice.

## Routes

| Route | Method | Kind | Response model | Called from (`web/src`) |
|---|---|---|---|---|
| `/api/activity/{activity_id}/race` | POST | command | no, 204 No Content, no body | rides.ts |
| `/api/analytics/compare` | GET | read | yes `RideCompare` | analytics.ts |
| `/api/analytics/power-model` | GET | read | yes `PowerModel` | analytics.ts |
| `/api/analytics/weight-trend` | GET | read | yes `WeightTrend` | analytics.ts |
| `/api/builder/preview` | POST | command | yes `BuilderPreview` | builder.ts |
| `/api/builder/save` | POST | command | yes `BuilderSaved` | builder.ts |
| `/api/builder/send` | POST | command | yes `BuilderSaved` | builder.ts |
| `/api/builder/workout` | GET | read | yes `BuilderLoaded` | builder.ts |
| `/api/calendar` | GET | read | yes `CalendarRead` | plan.ts |
| `/api/calendar/push-workout` | POST | command | yes `WorkoutPushed` | plan.ts |
| `/api/daily-log` | GET | read | yes `DailyLogRead` | home.ts |
| `/api/daily-log` | POST | command | yes `DailyLogSaved` | home.ts |
| `/api/diag/frontend-error` | POST | command | yes `FrontendErrorLogged` | errorReport.ts |
| `/api/diag/health` | GET | read | yes `DiagHealth` | settings.ts |
| `/api/diag/recent-errors` | GET | read | yes `DiagErrors` | settings.ts |
| `/api/download/zwo/{filename}` | GET | read | no, file download | library.ts, plan.ts |
| `/api/event/projection` | GET | read | yes `EventProjection` | wellness.ts |
| `/api/export/backup` | GET | read | no, file download (tar.gz) | YourData.tsx |
| `/api/export/fit-workout` | GET | read | no, file download (FIT) | plan.ts |
| `/api/export/{table}.csv` | GET | read | no, file download (CSV) | YourData.tsx |
| `/api/fueling` | GET | read | yes `Fueling` | nutrition.ts |
| `/api/icu/athlete-numbers` | GET | read | yes `AthleteNumbers` | firstRun.ts |
| `/api/icu/connection` | GET | read | yes `IcuConnection` | setup.ts |
| `/api/icu/disconnect` | POST | command | yes `Ok` | settings.ts |
| `/api/icu/push` | GET | read | yes `IcuPushStatus` | settings.ts |
| `/api/icu/push` | POST | command | yes `IcuPushResult` | settings.ts |
| `/api/icu/races` | GET | read | yes `IcuRaces` | plan.ts |
| `/api/injury` | GET | read | yes `InjuryStatus` | injury.ts |
| `/api/injury/episodes` | POST | command | yes `InjuryStatus` | injury.ts |
| `/api/injury/episodes/{episode_id}` | DELETE | command | yes `InjuryStatus` | injury.ts |
| `/api/injury/episodes/{episode_id}/resolve` | POST | command | yes `InjuryStatus` | injury.ts |
| `/api/injury/ramp-rate` | GET | read | yes `RampRate` | injury.ts |
| `/api/insights/ask` | POST | command | yes `Insight` | coach.ts |
| `/api/insights/ride/{ride_id}` | POST | command | yes `Insight` | coach.ts |
| `/api/insights/week` | POST | command | yes `Insight` | coach.ts |
| `/api/llm` | DELETE | command | yes `LlmConnection` | coach.ts |
| `/api/llm` | GET | read | yes `LlmConnection` | coach.ts |
| `/api/llm` | POST | command | yes `LlmConnection` | coach.ts |
| `/api/llm/test` | POST | command | yes `Insight` | coach.ts |
| `/api/logs` | GET | read | yes `LogTail` | settings.ts |
| `/api/metrics/history` | GET | read | yes `MetricPoint` (list) | wellness.ts |
| `/api/migrations/last-run-result` | GET | read | yes `MigrationResult` | wellness.ts |
| `/api/notifications` | GET | read | yes `NotificationList` | notifications.ts |
| `/api/notifications/read` | POST | command | yes `NotificationList` | notifications.ts |
| `/api/notifications/settings` | GET | read | yes `NotificationSettings` | notifications.ts |
| `/api/notifications/settings` | PUT | command | yes `NotificationSettings` | notifications.ts |
| `/api/notifications/test` | POST | command | yes `NotificationTest` | notifications.ts |
| `/api/nutrition/connection` | DELETE | command | yes `NutritionConnection` | nutrition.ts |
| `/api/nutrition/connection` | GET | read | yes `NutritionConnection` | nutrition.ts |
| `/api/nutrition/connection` | POST | command | yes `NutritionConnection` | nutrition.ts |
| `/api/nutrition/sync` | POST | command | yes `NutritionSync` | nutrition.ts |
| `/api/nutrition/test` | POST | command | yes `NutritionTest` | nutrition.ts |
| `/api/picker` | GET | read | yes `PickerResult` | library.ts |
| `/api/plan` | GET | read | yes `PlanRead` | home.ts |
| `/api/plan/accept-redraw` | POST | command | yes `RedrawAccepted` | home.ts |
| `/api/plan/add-race` | POST | command | yes `RaceAdded` | home.ts |
| `/api/plan/auto-adjust` | POST | command | yes `AutoAdjustResult` | home.ts |
| `/api/plan/auto-recalc` | POST | command | yes `PlanAutoRecalc` | plan.ts |
| `/api/plan/continuous/deload-revert` | POST | command | yes `DeloadReverted` | home.ts |
| `/api/plan/daily-adapt` | GET | read | yes `DailyAdapt` | plan.ts |
| `/api/plan/dismiss-session` | POST | command | yes `SessionDismissed` | home.ts |
| `/api/plan/entry-scan` | GET | read | yes `EntryScan` | plan.ts |
| `/api/plan/ftp-test-type` | POST | command | yes `FtpTestTypeSet` | home.ts |
| `/api/plan/generate` | POST | command | yes `PlanRead` | home.ts |
| `/api/plan/mark-unavailable` | POST | command | yes `UnavailableMarked` | home.ts |
| `/api/plan/move-session` | POST | command | yes `SessionMoved` | home.ts |
| `/api/plan/preview` | GET | read | yes `PlanPreview` | plan.ts |
| `/api/plan/preview-redraw` | POST | command | yes `RedrawCandidate` | home.ts |
| `/api/plan/reforecast` | POST | command | yes `PlanReforecasted` | plan.ts |
| `/api/plan/regenerate` | POST | command | yes `PlanRegenerated` | home.ts |
| `/api/plan/rematch` | POST | command | yes `RematchResult` | home.ts |
| `/api/plan/save-availability` | POST | command | yes `AvailabilitySaved` | home.ts |
| `/api/plan/swap-type` | POST | command | yes `SessionSwapped` | home.ts |
| `/api/plan/update` | POST | command | yes `PlanUpdated` | plan.ts |
| `/api/profile/backfill-history` | POST | command | yes `BackfillHistoryStarted` | settings.ts |
| `/api/profile/backfill-history/status` | GET | read | yes `BackfillHistoryStatus` | settings.ts |
| `/api/profile/dfa-alpha1` | GET | read | yes `DfaSnapshot` | dfa.ts |
| `/api/profile/dfa-backfill/cancel` | POST | command | yes `DfaBackfillCancelRequested` | dfa.ts |
| `/api/profile/dfa-backfill/status` | GET | read | yes `BackfillStatus` | dfa.ts |
| `/api/profile/dfa-rides` | GET | read | yes `DfaRides` | dfa.ts |
| `/api/profile/fatigue-resistance` | GET | read | yes `FatigueResistance` | analysis.ts |
| `/api/profile/ftp-history` | GET | read | yes `FtpHistory` | wellness.ts |
| `/api/profile/power-curve` | GET | read | yes `PowerCurve` | analysis.ts |
| `/api/profile/pr-toast-queue` | GET | read | yes `PrToastQueue` | rides.ts |
| `/api/profile/tau-fits` | GET | read | yes `TauFits` | analysis.ts |
| `/api/profile/update-ftp` | POST | command | yes `FtpUpdated` | rides.ts |
| `/api/profiles` | GET | read | yes `ProfilesList` | AppShell.tsx, profiles.ts |
| `/api/profiles/create` | POST | command | yes `ProfileCreated` | setup.ts |
| `/api/profiles/switch` | POST | command | yes `ProfileSwitched` | profiles.ts, setup.ts |
| `/api/profiles/{profile_id}` | DELETE | command | yes `Ok` | profiles.ts |
| `/api/profiles/{profile_id}` | PUT | command | yes `Ok` | profiles.ts |
| `/api/programme/summary` | GET | read | yes `ProgrammeSummary` | home.ts |
| `/api/programme/summary/png` | GET | read | no, image | plan.ts |
| `/api/races` | GET | read | yes `RacesStatus` | races.ts |
| `/api/races` | POST | command | yes `RacesStatus` | races.ts |
| `/api/races/sync` | POST | command | yes `RacesStatus` | races.ts |
| `/api/races/{race_id}` | DELETE | command | yes `RacesStatus` | races.ts |
| `/api/races/{race_id}` | PUT | command | yes `RacesStatus` | races.ts |
| `/api/races/{race_id}/race-day` | GET | read | yes `RaceDayPlan` | races.ts |
| `/api/readiness` | GET | read | yes `Readiness` | home.ts |
| `/api/readiness/apply-tier-down` | POST | command | yes `TierDownApplied` | home.ts |
| `/api/readiness/revert-cap` | POST | command | yes `CapReverted` | home.ts |
| `/api/retest-nudge/snooze` | POST | command | yes `RetestSnoozed` | wellness.ts |
| `/api/ride/import` | POST | command | yes `RideImported` | rides.ts |
| `/api/ride/{ride_id}/detail` | GET | read | yes `RideDetail` | rides.ts |
| `/api/ride/{ride_id}/ftp-test-analysis` | GET | read | yes `FtpTestAnalysis` | rides.ts |
| `/api/ride/{ride_id}/ftp-test-review` | POST | command | yes `FtpReviewSaved` | rides.ts |
| `/api/ride/{ride_id}/rpe` | POST | command | yes `RideRpeSaved` | rides.ts |
| `/api/rider-stats` | GET | read | yes `RiderStats` | home.ts |
| `/api/rides` | GET | read | yes `RideSummary` (list) | analysis.ts |
| `/api/rides/sync` | POST | command | yes `RidesSynced` | rides.ts |
| `/api/rides/{ride_id}` | DELETE | command | yes `Ok` | rides.ts |
| `/api/rides/{ride_id}/fit` | GET | read | no, file download (FIT) | rides.ts |
| `/api/run/activities` | GET | read | yes `RunActivities` | run.ts |
| `/api/run/critical-speed` | POST | command | yes `CriticalSpeed` | run.ts |
| `/api/run/gap` | GET | read | yes `RunGap` | run.ts |
| `/api/run/predict` | GET | read | yes `RacePredictor` | predict.ts |
| `/api/run/zones` | GET | read | yes `RunZones` | run.ts |
| `/api/settings` | GET | read | yes `SettingsRead` | settings.ts |
| `/api/settings` | POST | command | yes `SettingsSaved` | settings.ts |
| `/api/settings/workout-folders` | GET | read | yes `WorkoutFolders` | settings.ts |
| `/api/settings/workout-folders` | POST | command | yes `WorkoutFolders` | settings.ts |
| `/api/settings/zones` | POST | command | yes `ZonesSaved` | settings.ts |
| `/api/setup/check-activities` | POST | command | yes `ActivitiesCheck` | firstRun.ts |
| `/api/setup/defaults` | GET | read | yes `SetupDefaults` | firstRun.ts |
| `/api/setup/ensure-profile` | POST | command | yes `EnsureProfile` | firstRun.ts |
| `/api/setup/limits` | GET | read | yes `SetupLimits` | setup.ts |
| `/api/setup/pick-folder` | GET | read | yes `PickedFolder` | firstRun.ts |
| `/api/setup/save` | POST | command | yes `SetupSaved` | setup.ts |
| `/api/setup/test-icu` | POST | command | yes `IcuKeyCheck` | setup.ts |
| `/api/sports/load` | GET | read | yes `SportsLoad` | sports.ts |
| `/api/sports/thresholds` | GET | read | yes `SportThresholds` | sports.ts |
| `/api/sports/thresholds` | POST | command | yes `SportThresholds` | sports.ts |
| `/api/swim/activities` | GET | read | yes `SwimActivities` | swim.ts |
| `/api/swim/css` | GET | read | yes `SwimCss` | swim.ts |
| `/api/swim/css-test` | POST | command | yes `SwimCssTest` | swim.ts |
| `/api/swim/open-water` | GET | read | yes `OpenWaterNotes` | swim.ts |
| `/api/swim/open-water` | POST | command | yes `OpenWaterNote` | swim.ts |
| `/api/swim/open-water/{note_id}` | DELETE | command | yes `Ok` | swim.ts |
| `/api/swim/open-water/{note_id}` | PUT | command | yes `OpenWaterNote` | swim.ts |
| `/api/sync` | POST | command | yes `SyncResult` | settings.ts |
| `/api/sync/progress` | GET | read | yes `SyncProgress` | dfa.ts |
| `/api/sync/status` | GET | read | yes `SyncStatus` | settings.ts |
| `/api/today-session` | GET | read | yes `TodaySession` | home.ts |
| `/api/today-session/persist` | POST | command | yes `TodayPersisted` | home.ts |
| `/api/update/check` | GET | read | yes `UpdateCheck` | settings.ts |
| `/api/version` | GET | read | yes `VersionInfo` | settings.ts |
| `/api/weather/forecast` | GET | read | yes `WeatherForecast` | weather.ts |
| `/api/weather/location` | DELETE | command | yes `WeatherLocation` | weather.ts |
| `/api/weather/location` | GET | read | yes `WeatherLocation` | weather.ts |
| `/api/weather/location` | PUT | command | yes `WeatherLocation` | weather.ts |
| `/api/weather/search` | GET | read | yes `WeatherSearch` | weather.ts |
| `/api/week-summary` | GET | read | yes `WeekSummary` | home.ts |
| `/api/wellness` | GET | read | yes `WellnessDay` (list) | analysis.ts |
| `/api/wellness/3d-fitness-status` | GET | read | yes `Fitness3dStatus` | wellness.ts |
| `/api/wellness/backfill-3d-fitness` | POST | command | yes `Backfill3d` | wellness.ts |
| `/api/wellness/hrv-recording-dismiss` | POST | command | yes `HrvPromptDismissed` | wellness.ts |
| `/api/wellness/hrv-recording-status` | GET | read | yes `HrvPromptStatus` | wellness.ts |
| `/api/wellness/import-hrv4training` | POST | command | yes `HrvImported` | wellness.ts |
| `/api/wellness/manual-hrv` | POST | command | yes `HrvSaved` | wellness.ts |
| `/api/workout/download/{filename}` | GET | read | no, file download | library.ts |
| `/api/workout/{category}/{filename}` | GET | read | yes `WorkoutDetail` | library.ts |
| `/api/workouts` | GET | read | yes `WorkoutRow` (list) | library.ts |
| `/api/workouts/tags` | GET | read | yes `WorkoutTags` | library.ts |
