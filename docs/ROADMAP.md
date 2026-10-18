# Roadmap (adopted 2026-10-18)

The GitHub issues are the source of truth for scope. This file orders them by release, records dependencies, and records owner decisions. It replaces the wave plan of 2026-10-17.

## Rules for every item
- One branch and PR per issue (or per tight group). Local gate (`tools/gate.sh`) green before merge. **#147 is split along these lines; nothing merges whole.**
- Before dispatching work, check that no other open PR covers the same issue or files (two multi-sport models, #147 vs #158, came from skipping this).
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

## 4.0.0: "Shepherd stands alone" (MAJOR: breaking changes and fixes, no new features)
| Issue | What |
|---|---|
| #26, #16 | macOS and Windows retired; AppImage and Docker are the release targets (from #147) |
| #153 | Non-root container (breaking: one-time volume ownership fix, command in the release notes) |
| #152 | Login throttling and expiring sessions (everyone signs in again once) |
| #154 | Lock on the data folder: one server process per data directory |
| #107 / #149 | CI green; required before anything else merges |
| #155 | Dependabot, `pip-audit`, `SECURITY.md` |
| #159 | Pre-release flag in release.yml, `:beta` image, breaking-change check, versioning docs |
| #31 | Phase-0 data protections (choose #150 or #147's version) |
| #162, #164 | Plan form A-event bug; test-order pollution |
| #139 | Zwift upload errors: an intervals.icu setting; Settings explains it (done), close once confirmed |

Pre-releases `4.0.0-beta.1`, then `4.0.0-rc.1`, upgrade-tested from a 1.0.1 backup (#160).

## 4.1.0: data foundation (MINOR)
| Issue | What | Depends on |
|---|---|---|
| #156 | Garmin direct: health data and activities (branch `claude/practical-brown-9ydn5d`) | 4.0.0 |
| #161 | Ingest contract: per-field precedence, one de-duplicated FIT path (takes in #147's folder importer), cache clearing after sync, sync health panel | #156 |
| #109 / #158 | Multi-sport model: **#158** (`sports.py`); port what's useful from #147's `multisport.py` | none |
| #163 | Parse each FIT once per request | #161 |

Beta `4.1.0-beta.N` on the owner's real Garmin and intervals.icu accounts for about 2 weeks (#160).

## 4.2.0: everyday experience (MINOR, pieces of #147 one PR each)
#145 at-a-glance home, #105 onboarding, #106 themes (**#151**; #147's version is dropped), #130 mobile and installable app, #131 notifications, #128 readiness on Garmin data (body battery, stress, Garmin readiness), #129 export and backup (leave out `garmin_tokens.json` and SparkyFitness keys), **#165 Garmin-only riders**.

## 4.3.0: nutrition (MINOR)
#112 SparkyFitness: background sync, self-signed HTTPS for home servers, fueling targets from planned load. Beta on the owner's real server.

## 4.4.0: tools (MINOR)
#110 workout builder, sending straight to the watch through Garmin (intervals.icu fallback) · #111 races and taper · #113 injury and illness · #114 weight and W/kg from Garmin, power-duration model · #116 ride comparison · #115 gear from Garmin's gear API · #117 weather (Open-Meteo, the rider's location).

## 4.5.0 onward: running and triathlon (MINORs, umbrella #133)
In order: #118 zones, #119 load, #120 run workouts, #121 race predictor, #122 swim, #124 sport balance, #123 bricks, #125 race-distance plans, #126 open-water notes, #127 strength and mobility. Each passes the science rule above. Turning companion sessions into real per-sport plan sessions needs #24. If the plan file changes in a way older versions can't load, that release is **5.0.0**.

## Ongoing (one slice per release)
#10 typed API (#157 error shape) · #23, #24 planner and calculation consolidation · #11 intensity ceiling (owner decision: floor or rail fix, moves golden cases) · #94 desktop parity · #9 browser tests · #13 server access (implemented on #147; remote OAuth callback unverified) · #132 rebrand (naming search, fork detach: owner actions).

## Owner decisions (2026-10-18)
- #147 is split into per-issue PRs.
- Multi-sport model: #158. Themes: #151.
- Semantic versioning; the next release is 4.0.0; 4.0.0 holds only breaking changes and fixes, and features follow as MINORs.
- Garmin is the source of health data and activity files; intervals.icu is the source of fitness numbers and planning; SparkyFitness is the source of nutrition.
- Garmin-only riders (no intervals.icu) come in 4.2.0, the minor after the Garmin release.

## What "done" means for the large items
A vertical slice that works end to end and is tested, with the remaining scope written on the issue, beats a wide unfinished layer. Each issue is closed only when its own checklist is met.
