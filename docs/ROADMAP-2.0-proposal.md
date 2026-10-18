# Roadmap proposal: Shepherd 2.0 (draft for owner approval, 2026-10-18)

Not adopted yet. On approval this replaces `docs/ROADMAP.md`, and the issue
changes listed at the end get made.

## Where data comes from in 2.0

| Data | Source | Notes |
|---|---|---|
| Sleep, HRV, resting HR, body battery, stress, steps, readiness | **Garmin Connect** (direct) | Garmin's value wins over intervals.icu's (built on `claude/practical-brown-9ydn5d`). |
| Activity files (FIT) | **Garmin Connect** (direct), plus upload and folder import | One import path, de-duplicated across every source. |
| Fitness numbers (CTL/ATL/eFTP), planning calendar, workouts sent to Zwift and others | **intervals.icu** | Can optionally receive Garmin activities from Shepherd if Garmin cuts it off (#31). |
| Nutrition and fueling | **SparkyFitness** API (#112) | Self-hosted, has a phone app. The #147 branch has a client slice. |
| Thresholds, check-ins, races, injuries | **The rider (manual)** | A manual value always beats a synced one. |

## Problems with the current roadmap

1. **The data plan is out of date.** It routes Garmin data through intervals.icu and parks #31 in "wave 4: external". Garmin direct is now the main source, so ingest is a foundation item, not wave 4.
2. **No release plan.** The waves have no version numbers, no beta stage and no rollback step. "Smooth rollout" isn't defined anywhere.
3. **The PR rule ("one branch and PR per issue") is being broken.** #147 is 262 files and touches ~25 issues as partial slices. It can't be reviewed or reverted in pieces.
4. **Parallel threads are duplicating work.** Two multi-sport models now compete: #158 adds `sports.py` while #147 adds `multisport.py`. Other duplicates against #147: #151 (themes, #106), #150 (#31 phase 0), #149 (CI, #107). The "who owns which file" rule isn't applied across threads.
5. **Foundations are behind the features built on them.** #109 (multi-sport model) is a "slice", yet run, swim, tri and companion sessions were built on top of it. `PlannedSession` has no sport field on the #147 branch, but #158 adds one.
6. **No validation stage.** Nothing in #147 has run against live intervals.icu, SparkyFitness, Open-Meteo or Garmin. The run, swim and strength numbers are marked "verify". The roadmap has no step for testing with real data before release.
7. **The audit's security findings aren't scheduled.** #152 (login brute force, unrevocable cookie), #153 (root container) and #154 (two processes on one data folder) matter more once the Docker image is published.
8. **Known defects have no issues.** The FIT file is parsed 4× per ride view, `planForm.ts` sends the A event to a route that refuses it, and test-order pollution breaks 17 account tests. They exist only as text in the #147 roadmap.
9. **No rule for which source wins per field.** It's implicit in code (COALESCE and the Garmin overlay) and nobody has written it down. With 4 sources (Garmin, intervals.icu, SparkyFitness, manual) plus 3 FIT paths (Garmin, folder, upload), duplicates and silent overwrites are the main risk.
10. **Stale and duplicate issues.** #1 and #20 are v1 umbrellas. #104 duplicates #133. #148 duplicates #117. #31 is superseded by #156 once Garmin direct lands.
11. **Garmin direct isn't used where it removes work.** python-garminconnect can upload and schedule workouts on the watch, read gear, and read weight and body composition. That simplifies #110 (no intervals.icu hop), #115 and #114.
12. **The monolith slows every PR.** `app.py` is 20k lines and `training_planner.py` is 16k. Every feature edits `app.py`, which is why parallel PRs conflict. #147 introduced `routes_*.py` modules but nothing makes that the rule.

## Proposed release train

**Branches:** `main` stays 1.x and only takes fixes. A `release/2.0` branch takes 2.0 work, one issue per PR, each passing the local gate. Docker publishes `:beta` from `release/2.0` and `:latest` from tags. 2.0.0 merges `release/2.0` into `main`.

### 1.1: safety and reliability (`main`, small PRs)
- #149 CI green (required before anything else merges).
- #152 login throttling and expiring cookie, #153 non-root image, #154 data-folder lock.
- #155 Dependabot + `pip-audit` + `SECURITY.md`.
- Known defects as issues (point 8). Fix the `planForm` A-event bug here.
- Pick one of #150 and #147's #31 phase 0 (the data-protection rules) and ship it in 1.1. It protects riders on 1.x too.

### 2.0-beta.1: data foundation
1. **Garmin direct** (`claude/practical-brown-9ydn5d`, #156) → PR into `release/2.0`.
2. **New issue: ingest contract.** Write down which source wins for each field, and use one FIT ingest path with de-duplication across Garmin, folder, upload and intervals.icu. Also: a sync health panel per source, and clearing the wellness cache after any sync.
3. **#109 multi-sport model:** one model only. Recommendation: **#158** (`sports.py`, 7 files, no migration), with the useful parts of #147's `multisport.py` ported onto it.
4. **Data format migration:** bump `DATA_FORMAT` if the layout changes, run an upgrade test from a 1.0.1 backup (#19 tooling), and document a rollback.

### 2.0-beta.2: everyday experience (taken from #147, one PR each)
- #145 at-a-glance home, #105 onboarding, #106 themes (**pick #151 or #147's version**), #130 mobile/PWA, #131 notifications.
- #128 readiness, now on Garmin data: show body battery, stress and Garmin readiness next to Shepherd's own.
- #129 export/backup. The backup must leave out `garmin_tokens.json` and SparkyFitness keys.

### 2.0-beta.3: nutrition + validation
- **#112 SparkyFitness** (decided): background sync, self-signed HTTPS for home servers, and fueling targets from the planned load.
- **Validation stage (new issue):** run each beta for 2 weeks on the owner's real Garmin, intervals.icu and SparkyFitness accounts. Exit criteria: no data loss, no duplicate rides, no source fighting another for a field, a clean upgrade from 1.x.

### 2.0.0 ship
Merge into `main`, tag, publish the Docker and AppImage builds, write release notes with "what changed in your data", and give the rollback steps.

### 2.1: tools (still carried as partial slices on the #147 branch)
- #110 workout builder, **sending workouts straight to the watch through Garmin**, with intervals.icu as a fallback.
- #111 races and taper, #113 injury and illness, #114 weight/W/kg (weight from Garmin), #116 ride comparison.
- #115 gear, **read from Garmin's gear API** instead of guessing from intervals.icu.
- #117 weather (close #148 into it).

### 2.2 or 3.0: running and triathlon (#133)
#118–#127 in the existing order, each behind the **science gate**: a cited method, reference values as tests, a stated confidence. Includes turning the planner's "companion sessions" into real per-sport sessions (needs #24).

### Ongoing, one slice per release
#10 typed API (#157 error shape), #23/#24 planner consolidation, #11 intensity ceiling (owner decision), #26 cleanup, #94 desktop parity, #9 browser tests.
Rule from 2.0: **new endpoints go in a `routes_*.py` module, not `app.py`.**

## Decisions for the owner
1. **#147:** split it into per-issue PRs against `release/2.0` (recommended), or merge it whole into `release/2.0`?
2. **Multi-sport model:** #158 (recommended) or #147's `multisport.py`?
3. **Themes:** #151 or #147's version?
4. **Branching:** use `release/2.0` with `:beta` images (recommended), or keep everything on `main` behind feature flags?
5. **Garmin-only riders (no intervals.icu) in 2.0?** Recommended: not until 2.1. Shepherd can compute load locally, but planning and calendar push need intervals.icu.

## Issue changes on approval
- **New:** ingest contract and source precedence; 2.0 migration and rollback; validation stage; three known defects (FIT parsed 4×, planForm A event, test-order pollution).
- **Close as superseded:** #1, #20 (v1 umbrellas), #104 (into #133), #148 (into #117). #31 closes once #156 ships, with the phase-0 rules kept.
- **Milestones:** create `1.1`, `2.0`, `2.1` and `2.2/3.0`, and assign issues as above.
- **Update:** #112 (SparkyFitness chosen), #110/#115/#114 (use Garmin direct).
