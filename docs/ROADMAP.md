# Roadmap (adopted 2026-10-18)

**The roadmap board is the GitHub project [Shepherd (#3)](https://github.com/users/PACE-1/projects/3/views/1).** It holds what is planned, its status and its release. This file holds the rules, the versioning policy, the owner decisions, and the known gaps of what has shipped. When the two disagree, the board wins for ordering and this file wins for rules.

## Rules for every item
- One branch and PR per issue (or per tight group). Local gate (`tools/gate.sh`) green before merge. No more multi-issue PRs like #147.
- Before starting work, check the board and the open PRs for anything already covering the same issue or files (#147 and #158 built two multi-sport models in parallel).
- Tests with the change: a failing test first for bugs, contract tests for new endpoints, vitest for new screens, one browser test per new screen.
- API changes: Pydantic response model, regenerate `tests/api_contract.json` and `web/src/api/schema.d.ts`. New endpoints go in a `routes_*.py` module, not `app.py`.
- Running and swim numbers need a source: a named published method, reference values from it as tests, and a stated confidence. No invented coefficients.
- Planner output changes (#11, #24, #111, #113, #125) go up for review rather than straight to merge.
- Every MAJOR and MINOR passes the rollout checklist (#160) before its stable tag.

## Where data comes from (from 4.1)

| Data | Source | Notes |
|---|---|---|
| Sleep, HRV, resting HR, body battery, stress, steps, readiness | **Garmin Connect** (direct, #156) | Garmin's value wins over intervals.icu's. |
| Activity files (FIT) | **Garmin Connect**, plus upload and folder import | One de-duplicated import path (#161). |
| Fitness numbers (CTL/ATL/eFTP), planning calendar, workouts sent to Zwift and others | **intervals.icu** | Can optionally receive Garmin activities from Shepherd (#31). |
| Nutrition and fueling | **SparkyFitness** API (#112) | Decided. |
| Thresholds, check-ins, races, injuries | **The rider** | A manual value always beats a synced one. |

The per-field precedence table belongs in `docs/DATA.md` (#161).

## Versioning: semantic versioning

**Next release: 4.0.0.** The repo still has the upstream project's tags v1.0.2 through v3.13.1 (including a v2.0.0), so the fork goes to the first number above them. The old tags stay as history. Tooling: #159.

**The public API (what a version number promises):** the data folder (layout, `DATA_FORMAT`, SQLite schema, JSON files); the `SHEPHERD_*` configuration and the Docker contract (port 22400, `/data` volume, user, required variables); the HTTP API documented in `docs/API.md` and `tests/api_contract.json`; the supported platforms (Docker on linux/amd64, the Linux AppImage).

| Bump | When |
|---|---|
| **MAJOR** | Something above breaks for an existing install or needs a manual upgrade step: dropping a platform, a migration that can't run on its own, a renamed variable with no alias, a removed API route or field, a container user change that needs a volume ownership fix. |
| **MINOR** | New features, backward compatible; data migrates forward automatically. Includes reviewed planner changes, noted in the release notes. |
| **PATCH** | Bug and security fixes only; no new settings, routes or data layout. |

- **Pre-releases:** `X.Y.Z-beta.N`, then `X.Y.Z-rc.N`. They are published as GitHub pre-releases, so the in-app update check never offers them to stable users.
- **Version source:** the `VERSION` file; the tag `vX.Y.Z` must match it. Changelog headings: `## vX.Y.Z — title (date)`.
- **Docker tags:** `:X.Y.Z` always; `:X.Y` and `:latest` for the newest stable; `:beta` for the newest pre-release.
- **Branches:** `main` is the release line. A MINOR is built up on `release/X.Y`, one PR per issue; patches land on `main` and are merged forward.
- **Downgrades** aren't promised across a MINOR or MAJOR: back up first. The release notes say so.

## Releases

### 4.0.0: what is on `main` now, made safe to ship (MAJOR)
`main` already holds #147: macOS/Windows retired (breaking), multi-sport load and thresholds, run/swim/strength companion sessions, the cycling workout builder, races, injury, gear, weather, SparkyFitness (on demand), notifications, phone layout, palettes, export, the Docker publish workflow. 4.0.0 ships that, plus:

| Issue | What |
|---|---|
| #153 | Non-root container (breaking: one-time volume ownership fix, command in the release notes) |
| #152 | Login throttling and expiring sessions (everyone signs in again once) |
| #154 | Lock on the data folder: one server process per data directory |
| #107 | CI green on GitHub Actions: lint fixed in #147, superseded runs cancelled (#149, merged); the bricks/triathlon browser test failed once and passed on re-run, so watch for a flake |
| #155 | Dependabot, `pip-audit`, `SECURITY.md` |
| #159 | Pre-release flag in release.yml, `:beta` image, breaking-change check, versioning docs |
| #31 | Phase-0 data protections: done (#147, and #150 merged: sync no longer prunes rides). The issue stays open for the Garmin route (#156, 4.1.0) |
| #164 | Test-order pollution |
| #26, #16 | Finish: the cleanup and lint pass, `NOTICE` still lists the trainer packages |
| #139 | Zwift upload errors: an intervals.icu setting; Settings explains it; close once confirmed |

No new features beyond what #147 already merged. Pre-releases `4.0.0-beta.1`, then `4.0.0-rc.1`, upgrade-tested from a 1.0.1 backup. The beta is the first time #147's features run against live services, so expect fixes (#160).

### 4.1.0: data foundation (MINOR)
| Issue | What | Depends on |
|---|---|---|
| #156 | Garmin direct: health data and activities (branch `claude/practical-brown-9ydn5d`) | 4.0.0 |
| #161 | Ingest contract: per-field precedence, one de-duplicated FIT path (Garmin, folder import, upload), cache clearing after sync, sync health panel | #156 |
| #109 | Multi-sport model on `main` (#147's `multisport.py`) with per-sport detail pages (#166, merged); remaining: zone-aware charts, run/swim sessions in the plan data | none |
| #163 | Parse each FIT once per request | #161 |

Beta `4.1.0-beta.N` on the owner's real Garmin and intervals.icu accounts for about 2 weeks (#160).

### 4.2.0: everyday experience (MINOR)
Remaining scope on #145, #130, #131 (web push, retries), #128 readiness on Garmin data (body battery, stress, Garmin readiness), #129 (restore from the UI), and **#165 Garmin-only riders**.

### 4.3.0: nutrition (MINOR)
#112 SparkyFitness, beyond the on-demand slice on `main`: background sync, self-signed HTTPS for home servers, fueling targets from planned load. Beta on the owner's real server.

### 4.4.0: tools (MINOR)
Remaining scope on #110 (send to the watch through Garmin; run and swim targets), #111 (run/swim races, segment pacing, fueling), #113, #114 (weight from Garmin; W/kg over time), #116, #115 (gear from Garmin's gear API), #117.

### 4.5.0 onward: running and triathlon (MINORs, umbrella #133)
Remaining scope on #118–#127 (the gaps in the tables below), each through the science rule. Turning companion sessions into real per-sport plan sessions needs #24. If the plan file changes in a way older versions can't load, that release is **5.0.0**.

### Ongoing (one slice per release)
#10 typed API (one error shape merged in #157; service extraction remains) · #23 (one FIT power reader merged in #167), #24 planner and calculation consolidation · #11 intensity ceiling (owner decision: floor or rail fix, moves golden cases) · #94 desktop parity · #9 browser tests · #13 server access (remote OAuth callback unverified) · #132 rebrand (naming search, fork detach: owner actions).

## Owner decisions (2026-10-18)
- #147 stays merged; the roadmap is re-planned around `main`. #158 and #151 are closed, so `main`'s multi-sport model and palettes are the ones going forward.
- Semantic versioning; the next release is 4.0.0 (what is on `main`, plus breaking and security fixes, no new features); features follow as MINORs.
- Garmin is the source of health data and activity files; intervals.icu is the source of fitness numbers and planning; SparkyFitness is the source of nutrition.
- Garmin-only riders (no intervals.icu) come in 4.2.0, the minor after the Garmin release.

## What "done" means for the large items
A vertical slice that works end to end and is tested, with the remaining scope written on the issue, beats a wide unfinished layer. Each issue is closed only when its own checklist is met.

## Status (2026-10-18) and known gaps

Everything below shipped on `main` with #147 (merged 2026-10-18) and goes out in 4.0.0. Each issue stays open until its own checklist is met; the gaps below are the remaining scope. "Verified" means unit/contract/browser tests passed in a container with no real riders' data and no live external services.

| Issue | State | Remaining scope (known gaps) |
|---|---|---|
| #107 CI | done locally | Not yet seen green on GitHub Actions. |
| #109 multi-sport model | slice | Per-sport detail pages and zone-aware charts; plan data is still cycling-only (`PlannedSession` has no sport field). |
| #110 workout builder | cycling only | Run and swim targets; `.fit` export; duplicate/delete; Edit link on Library rows. |
| #111 race planner | slice | Run/swim races; segment pacing; fueling in the race-day plan (comes from #112); nav link to `#/races`. B races now taper (7 days at 60%): changes plans of riders who already have B races, needs review. |
| #112 fueling | slice | SparkyFitness endpoints verified from its source, never run against a live server. On-demand sync only (no background sync); no targets pushed back; https with self-signed certificates fails. |
| #113 injury/illness | slice | A short illness (under 15 days) gets no forced return ramp: the planner's short-break rule (`SCIENCE.md` 1b) applies and the rider ends the pause with "I'm back" when they feel well. Injuries and illnesses of 15+ days keep the easy-only ramp. Nothing rebuilds the plan when an episode's end date passes; only the cycling plan pauses; no nav link to `#/injury`. |
| #114/#116 analytics | slice | W/kg for 5- and 20-minute power over time; cadence/speed/elevation/zone comparison; runs. |
| #117 weather | slice | Every non-rest session counts as outdoor (plans have no indoor flag); the whole riding day is rated (sessions have no time of day); thresholds are heuristic defaults; extra-rider wizard has no location step. |
| #118/#119 run | slice | Run pace/gradient streams are not stored, so rTSS uses average pace (low on hilly or interval runs); grade adjustment only in the converter; nothing checked against real recorded runs; cadence only, no ground-contact time. |
| #121 race predictor | slice | "What fitness change reaches a target time"; checking predictions against real race results; the card does not refresh after a critical-speed save until Settings reloads. |
| #122/#126 swim | slice | No swim pace zones (no citable exact percentages); sTSS uses average speed (low to moderate confidence); no stroke count or SWOLF in intervals.icu data; open-water notes are not surfaced in race-week planning (needs the planner). |
| #128 readiness | slice | Sleep trends and illness warning signs; runs/swims without an intervals.icu load count as zero. |
| #129 export | slice | Restore from the UI stages a verified backup and applies it at the next start (no in-place swap while running). |
| #131 notifications | slice | No web-push or email; no per-event channel choice; failed ntfy posts are not retried. |
| #115 gear | slice | Auto-assign from intervals.icu reads `gear.name` best-effort (the field is unverified here); no matching on `gear.id`; a due item raises one bell notice (and ntfy) but has no Home entry; gear is not shown on the ride page. |
| #124 sport balance | actuals only | Planner emphasis toward a limiter (needs the multi-sport planner decision); cross-sport load shares are indicative (each sport's load has its own scale). |
| #11 planner audit | audit done, no planner change | The intensity-ceiling expectedFailure is still valid (7 of 864 property-test weeks): cause and two measured prototype fixes are in `docs/PLANNER_AUDIT.md`; choosing the floor-or-rail fix is an owner decision because it moves golden cases. Sealing is dormant in production. |
| #10 typed API | slice | 8 UI-called routes remain without a model (7 file/image downloads and one 204), each with a stated reason; no service extraction yet. |
| #26/#16 release | decided | macOS/Windows retired; Linux (Docker, AppImage) only; GitHub is the release identity. No Docker image publish step yet (registry and tag policy to decide). Final cleanup/lint pass planned before the next major version. |

Known defects (tracked):
- #163: one ride-detail load parses the same FIT file four times.
- #164: test-order pollution; `test_api_contract.py` before `test_account_core.py` in one process fails 9 tests.
- (The plan-form A-event bug, #162, was fixed in #147.)
- Not started (need a design decision): #123 bricks, #125 race-distance plans, #127 strength sessions, run/swim sessions in the plan. They depend on how a plan holds non-cycling sessions.
- #132 rebrand: README rewritten (install, platforms, configuration, first run, update, backup). Still open and not doable from here: the naming/trademark availability search (GNU Shepherd and Shepherd.js exist) and detaching the GitHub fork network (a GitHub account action). `NOTICE` still lists third-party packages (bleak, pycycling, openant) from the removed trainer subsystem; fix in the cleanup pass.
- #13 server access: implemented (`src/access.py`, `docs/SERVER.md`, `tests/test_access_control.py`). Not verified: that intervals.icu accepts a remote-browser OAuth callback (use the API-key connection on a server).
- #132 naming: `docs/NAMING.md` records the name-collision search (GNU Shepherd exists; no registered mark found, which is not a clearance) and what the owner still has to check. Fork detach: owner action, permanent, may lose issues: see that doc before doing it.
- #31 Garmin block: a listed-but-withheld ride (sport and length present, no load/power/HR) now completes a planned session; one sync-health notice per episode (needs evidence); setup copy neutral; folder importer in Settings. Not verified against a real block (the shape of a withheld Garmin ride is assumed). Not done: upgrading sessions already marked "partly done" (needs the planner); in Docker the clock may be UTC while intervals.icu start times are local, so a duplicate can be missed by the offset; in server mode the folder setting reveals whether a path exists (revisit with #13).

## Multi-sport planning (companion sessions), built 2026-10-18

Design: `docs/ROADMAP.md` history and the owner-approved ADDENDUM 5 (a `companions` list per plan week, opt-in through the rider's saved sport split; the cycling solver is untouched; cycling-only plans are byte-identical).

| Issue | State | Remaining scope |
|---|---|---|
| #120 run library | built | Design templates after Daniels; several figures marked "verify"; never checked against recorded runs or imported into a Garmin; no HR targets. |
| #122 swim sessions | built | No pace zones (none citable); set shapes are coaching-practice templates. |
| #127 strength | built | Only the ACSM 2009 novice range is from the paper; other ranges are marked "verify". Mobility is labelled separately. No training stage reaches the builder (always the novice stage; no rider stage data exists). |
| #123 bricks | built | "Key ride", one brick a week and the placeholder run durations have no citation. |
| #124 limiter | built | The limiter claims hard slots and the longest day; no hours move beyond the rider's own split. |
| #125 triathlon plans | label only | A triathlon race takes a distance label (sprint/olympic/70.3/ironman/custom). No distance-specific volumes, phase lengths or weekly-hours tables: they need a citable source. The plan toward it uses the rider's own hours and split. |
| #111 run/swim races | label only | Non-cycling B/C races still take the cycling B taper and replace that day's ride; the race-day plan stays cycling-only. |

Engine caveats: `brick_of`, `brick_note` and `limiter` live inside a companion's `workout` dict (the planner dataclass has no fields for them; promote them when `training_planner.py` is next opened); companions add no load number (`tss_estimate` 0); reforecast, refit and daily-adapt still use the full weekly hours for cycling; moving a companion and undoing a dismiss are not built.
