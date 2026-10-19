# Cleanup closeout review

> **Historical record, measured at `0e3a10c2`. Not current status.** Since then the legacy `src/templates` were removed and the web UI replaced them, so the template line counts and the "UI consolidation" row below no longer describe `main`. Re-measure with `tools/arch/report.py` before quoting a number.

Reviewed merged `clean-main` at `0e3a10c2` (PRs #32–#52). The initial dead-code
batches are complete. The broader reduction/consolidation effort remains open;
merged PR count is not a completion metric.

## Current source size

Physical text lines, including comments and blank lines, counted with
`len(path.read_text().splitlines())` on tracked files. This is not executable
LOC. Binary assets, workout/route data, dependency installs and build output are
excluded. These categories are disjoint.

| Category | Files | Lines |
|---|---:|---:|
| Runtime Python (`src/*.py`) | 56 | 63,782 |
| Legacy templates (`src/templates`, HTML/CSS/JS) | 4 | 23,343 |
| First-party static JS/CSS/HTML (excluding vendor) | 2 | 1,224 |
| Web source (`web/src`, excluding tests, generated schema and `components/ui`) | 18 | 2,401 |
| **Maintained application source subtotal** | **80** | **90,750** |
| Web generated schema / UI component library | 7 | 1,132 |
| Python generation scripts (`src` subdirectories) | 4 | 3,455 |
| Python tests (`tests/**/*.py`) | 399 | 87,740 |
| Web tests (`web/src/**/*.test.*`) | 4 | 459 |

This subtotal excludes development tools outside `src`, packaging, configuration
and documentation. It is not a whole-repository LOC claim. The earlier
`measurements.md` snapshot predates the final API, backup and switch-gate merges.
The AST tool uses `split("\n")`, so its module counts include an extra trailing
line relative to this table for newline-terminated files.

Using exactly the same categories at `11cc77cb` gives 87,631 maintained
application lines (63,064 runtime Python, 23,343 templates and 1,224 static).
The merged tree has grown by **3,119 lines**, about 3.6%, principally from the
new web app and server/data-safety infrastructure. Dead-code removal is real,
but these PRs have not yet delivered a net reduction in maintained source.

## Complexity priorities

Read-only analysis: `python3 tools/arch/astmap.py src > /tmp/src.json`, then
`python3 tools/arch/report.py /tmp/src.json src/templates/dashboard.html`.
The reported complexity is a branch-node count, including nested functions;
it is a prioritisation signal rather than a standard cyclomatic measurement.

| Target at merged baseline | Span / complexity | Recommended bounded follow-up |
|---|---|---|
| `training_planner.sample_week_workouts` | 1,080 / 284 | Separate pool eligibility, candidate scoring and final week reconciliation. Preserve RNG draw order, state mutation order and serialized planner fingerprints. |
| `app._build_programme_summary` | 449 / 189 | Separate metric-window selection and pure summary calculations from database/profile reads. Preserve empty and continuous-plan behavior with existing summary endpoint tests. |
| `structure_fidelity.score_blocks` | 515 / 153 | Separate block scoring by block type while preserving the aggregate result and fallback behavior. |
| `training_planner.reforecast` | 712 / 148 | First make shared sizing/budget ownership explicit across generation, regeneration, recalculation, extension and refit; avoid another parallel policy implementation. |

Start the next larger refactor with the programme-summary builder: its existing
`test_programme_summary*.py` endpoint/data tests provide a smaller boundary for
separating reads from calculations. The sampler has the highest measured
complexity, but requires stricter RNG/state characterization before changing
its structure. No new summary or planner behavior is implemented in this PR.

`app.py` is 20,845 physical lines and `training_planner.py` is 16,415: together
37,260, or 58.4% of runtime Python. Merely moving these functions to another
module will improve navigation but will not reduce total LOC or branch count.

Nine AST clone groups were reported at baseline. They are not nine confirmed
logic duplicates: the profile setter group consists of already-consolidated
one-line calls with lengthy docstrings, and the OOS simulator deliberately
keeps an independent implementation. Do not consolidate those on shape alone.

## Implemented follow-up: migration persistence

Two migration writers still duplicated tmp-file, fsync, replace and cleanup
logic after the shared atomic-write PR. Both now delegate to
`atomic_io.write_json_atomic`, retaining their existing entry points and JSON
format. The shared module has no profile-manager/config import, so migration
startup ordering is preserved.

- Production source: **38 fewer lines**; maintained application subtotal becomes
  **90,712**, runtime Python **63,744**.
- Each migration writer's branch-node complexity drops from 8 to 1.
- The duplicate migration writer clone group disappears (9 groups to 8).
- Temp files are unique and private (0600 via `mkstemp`), rather than sharing a
  predictable `.tmp` name created with 0644 subject to umask. A leftover old
  `.tmp` file is left alone. This is an intentional filesystem detail change.
- Failure tests check that a failed rename preserves the existing data and
  removes the newly created temp file; stale-temp tests check that an old
  migration temp file is not reused. Existing migration/profile tests remain.

## Completion ledger

| Workstream | State / evidence needed to close |
|---|---|
| Verified dead-code batches | Implemented in #33/#41; remaining ledger candidates have tests or unresolved ownership/consumer contracts. |
| Shared persistence ownership | #44 implemented most paths; this follow-up removes two remaining migration copies. |
| UI consolidation | Open. `App.tsx` implements DFA and routes the other seven dashboard tabs to `NotMigrated`; legacy templates are unchanged from `11cc77cb`. Finish workflow parity before removing legacy templates. |
| Planner and summary complexity | Open. Priorities and required behavior protections are above. |
| Profile context | Partial. #51 orders switches against writes but explicitly leaves process-global profile/path/credential ownership and client header handling open. |
| Artifact/performance reduction | Open. Docker was measured at 658 MB; comparable startup/peak-memory and AppImage measurements are absent. |
| Final validation | Local changed-tree Linux gate and web checks pass after the test-isolation fix; merged-head baseline failures and remote-CI limits are recorded below. |

No UI or planner workstream is silently retired by this review. No live rider
files, service, public endpoints, migrations or product assets are removed.

## Verification

- Focused migration/profile/atomic checks: **54 passed**.
- Expanded migration/profile/job/access/backfill checks after the harness fix:
  **77 passed**. Access → DFA → calendar → backfill → power-curve sequence:
  **30 passed**.
- Web: frozen install, typecheck (`tsc -b`), lint, **28 tests passed**, build passed.
- Untouched merged-head baseline: **4 failed, 3,985 passed**, 7 skipped,
  20 expected failures, 13 non-strict unexpected passes and 26 passed subtests;
  serial **3 passed**. Status `bulk=1`, `serial=0`, `exit=1`.
- Initial migration-only full run: **7 failed, 3,986 passed**, same skip/expected
  result counts; serial **3 passed**. It shifted xdist scheduling and exposed
  the same job-stop leak in DFA/calendar as well as power-curve backfill.

The failure mechanism is test-process state: `TestClient` lifespan shutdown calls
`jobs.shutdown`, leaving `jobs.stopping()` true. Later tests skip backfill or
cancel DFA work. A short negative-control sequence on untouched `0e3a10c2`
(`test_access_control.py`, `test_backfill_sync_gate.py`, `test_power_curve_e2e.py`)
reproduced all four baseline failures (13 passed). The same sequence plus the
DFA/calendar suites passes after the shared harness drains cooperative jobs
and resets the jobs singleton following shutdown. No production cancellation
check or existing assertion was removed.

Local logs: `/tmp/shepherd-gate/merged-head-baseline.*`,
`migration-consolidation.*`, and `cleanup-closeout-final.*`. Repeat the gate with
an installed locked headless environment:

```sh
GATE_PYTHON=/path/to/headless/bin/python GATE_WORKERS=4 GATE_RERUN_FAILURES=0 \
  bash tools/gate.sh "$PWD" cleanup-closeout-final
```

Final full gate at the code in `b3db06d2`: **3,993 bulk passed**, 7 skipped,
20 expected failures, 13 non-strict unexpected passes and 26 passed subtests;
**3 serial passed**. Status: `bulk=0`, `serial=0`, `exit=0`.
The bulk took 559.56 seconds; the serial tail took 3.80 seconds. This is local
Linux verification, not a claim that the final merged head or platform artifacts
have passed remote CI. The proposed code/test fix must land before merged-head
validation can be considered closed.
