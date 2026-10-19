# Planner audit: shared invariants by entry point (#11)

> **Historical, measured at `24ab59e`.** Later, the rail was made to win over the floor (`_enforce_z5plus_share_ceiling` sheds a floor class last, not never) and the intensity-ceiling `expectedFailure` was removed. "No planner behaviour was changed" and the section 2 counts describe `24ab59e`, not `main`.

Measured on 2026-10-18 at `24ab59e` (branch `claude/peaceful-bell-wcwgkb`).
**No planner behaviour was changed.** `src/training_planner.py` is identical to
`24ab59e`, the characterization golden is unchanged (49 builders, 79 owner0,
79 owner1, all unchanged before and after), and the
`expectedFailure` stays. This extends the static map in
[code-bloat/planner-audit.md](code-bloat/planner-audit.md) and
[code-bloat/planner-entrypoints.md](code-bloat/planner-entrypoints.md) with
runtime measurements. Everything below was measured unless it is marked
**not reproduced**.

## How it was measured

- **Inputs.** The characterization drivers in `tests/_gate_env.py`:
  - a frozen clock (2026-09-14, a Monday, moved explicitly per driver);
  - athlete FTP 240 W and 72 kg; athlete id pinned to `gate-athlete`; seed 20260914;
  - explicit CTL and weekly TSS; an empty data home; no network.
- **Cases.** 73 plan-returning golden cases plus 6 hook cases:
  - **#113 injury:** a 10-day illness that ended 3 days before a regenerate.
  - **#111 B race:** a B race on load week 7, driven through generate, regenerate,
    recalculate, refit and reforecast.
- **Mode.** Production mode (`_USE_TRAINING_WEEK = False`), unless a section says
  owner mode.
- **Reproduction.** `tests/test_planner_invariants.py` (151 tests, about 13 s)
  reproduces every fact pinned below on a 21-case subset. The full-matrix numbers
  came from scratch scripts over the same drivers; those scripts were not committed.
- **Hash seed.** Results are identical with `PYTHONHASHSEED` 0 and 12345 over all
  79 cases.
- **Property-test numbers.** These use the construction in
  `tests/test_tid_plan_properties.py`:
  - riders: 6 h, 12 h and 18 h shapes;
  - models: pyramidal, polarized and threshold;
  - pinned "today" 2026-09-14, run under the pytest sandbox;
  - only full non-stepback weeks are counted;
  - swept over seeds 1 to 8, giving 864 full weeks.

## Switches (read from source, unchanged)

| Switch | Value | Where |
|---|---|---|
| `_USE_TRAINING_WEEK` | `False` | `src/training_planner.py:6553` |
| `_GENERATE_WHEN_LIBRARY_MISSES` | `False` | `src/training_planner.py:6554` |
| `_REPAIR_MAX_MOVES` | `0` | `src/training_planner.py:6702` |
| `_USE_WEEK_SOLVER` | `False` | `src/training_planner.py:6744` |
| `STRICT_SEAL` | `False` | `src/week_plan.py:177` |

## 1. Invariants by entry point (production mode, 79 cases)

Each check covers weeks ending on or after the case's "today". Counts are
violating weeks, with cases in brackets.

| Invariant | generate (26) | regenerate (16) | recalculate (3) | extend (10) | refit (17) | reforecast (6) | injury regen (1) |
|---|---|---|---|---|---|---|---|
| z5+ ≤ 18 %, full load weeks | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| z5+ ≤ 18 %, short (2-day) weeks | 1 | 0 | 1 | 0 | 0 | 0 | 0 |
| HIT ≤ phase `hit_count_max`, load weeks | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| no HIT on a stepback week, ignoring the FTP test | 0 | 0 | 0 | 0 | 2 (harness) | 0 | 0 |
| rest days respected (`plan_invariants`) | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| session ≤ day cap (`plan_invariants`) | 0 | 0 | 0 | 0 | 0 | 2 (override) | 0 |
| A-race taper week ≤ `TAPER_FRACS` × reference × 1.05, race excluded | 0 of 52 taper weeks across all event cases | | | | | | |

"reforecast" here covers `reforecast` (2 cases), `reforecast` with a TSB crash
(2) and the stored-plan `reforecast_dict` (2).

Reading the table, measured facts only:

- **Short weeks over the line.** These are `event/wkend3h/generate-thu`
  (week 13, peak, 20.8 %) and `event/wkend3h/recalculate@21` (week 13, build2,
  25.0 %). Each is the 2-day stub week before the taper.
  - The rail runs on them, but the only z5+ carrier is a class on its phase
    floor, which `_enforce_z5plus_share_ceiling` never sheds.
  - The property test does not count short weeks.
- **HIT cap.** It holds on every entry point, including regenerate, refit and
  reforecast. Those three never call `_enforce_weekly_hit_cap`, but nothing they
  built here needed it.
  - The static gap in code-bloat/planner-audit.md is therefore **not
    reproduced** as a defect. It is not proven absent either (see "The
    enforcement passes do not bind" below).
- **Stepback weeks.** Their cap is 0. The scheduled FTP test counts but is
  never demoted (3.3.1 hotfix), and it is the only HIT on any stepback week
  except in two `refit@24` cases.
  - In those two, the harness's `miss_a_hard_day` relabels a session as vo2max
    in a stepback week that had none. Refit then re-serves the missed hard day
    later in the same stepback week.
  - Refit does not check stepback status when it re-serves a missed hard
    session. From a real plan this is **not reproduced**: no real stepback week
    carried a hard session to miss.
- **Day cap.** The two flags are both `reforecast@21`, which is driven with a
  per-day override that frees 3 h on a 2 h weekday.
  - `plan_invariants.check_daily_duration_cap` reads the goal's caps, not the
    override. The flagged session is the one the override allowed.
- **Taper.** Checked naively, the race week looks over its ceiling only because
  the race session itself is in it. Excluding the race, every taper week is
  within the pass's own tolerance.

`plan_invariants.audit` findings per entry point, from the same run. These are
already recorded per case in `tests/characterization.json` under `inv`:

| Rule | generate | regenerate | recalculate | extend | refit | reforecast |
|---|---:|---:|---:|---:|---:|---:|
| weekly_volume | 3 | 11 (+1 injury) | 0 | 2 | 0 | 0 |
| hard_share | 3 | 7 | 2 | 1 | 1 | 0 |
| under_delivery | 3 | 1 | 0 | 1 | 5 | 2 |
| stepback_lightest | 1 | 1 | 1 | 0 | 1 | 1 |

Regenerate carries the most volume overshoot (11 weekly_volume findings in 16
cases against 3 in 26 for generate). This audit did not root-cause that.

### The enforcement passes do not bind on any measured case

Each pass below was switched off at runtime (scratch plugin, never committed):

| Pass removed | golden owner0 | golden owner1 | 864 property-test weeks |
|---|---|---|---|
| `_enforce_z5plus_share_ceiling` | 0 of 79 changed | 1 changed (`ctl/target60/regenerate@17`) | 0 changed |
| `_enforce_weekly_hit_cap` | 0 of 79 changed | 0 changed | 0 changed |

On the current tree, in production mode, neither pass changes a single plan
measured here. A passing suite therefore says nothing about them. The golden
cannot see either pass being removed, and before this audit no test called
`_enforce_z5plus_share_ceiling` directly.

`tests/test_planner_invariants.py` now exercises the rail directly: an
over-line week outside a floored phase is brought under 18 %.

The issue's 2026-10-16 note says the rail (`1f16054`, "#80" in that note) narrowed the
expected failure from 4 weeks to 1. That narrowing is **not reproduced** here:
the rail is inert on all 864 weeks. The one golden line `1f16054` blessed is
`ctl/target60/regenerate@17` in owner mode, which matches the table above.

## 2. The intensity-ceiling expected failure

`tests/test_tid_plan_properties.py::test_no_week_breaches_the_intensity_ceiling`
is still a valid expected failure. It fails today on 2 weeks, not the 1 its
docstring names:

- 6 h pyramidal, build2 week 9: 20.7 % of minutes at z5+ (the docstring does
  not mention it);
- 6 h threshold, build2 week 10: 18.4 % (the week the docstring names).

Swept over seeds 1 to 8 with the same construction, 7 of 864 full weeks breach:

| Seed | Rider | Model | Week | z5+ |
|---|---|---|---|---:|
| 1 | 6 h | threshold | build1 wk 7 | 18.5 % |
| 3 | 6 h | pyramidal | build2 wk 9 | 20.7 % |
| 3 | 6 h | threshold | build2 wk 10 | 18.4 % |
| 6 | 12 h | polarized | build1 wk 5 | 18.7 % |
| 7 | 6 h | pyramidal | build1 wk 5 | 18.4 % |
| 8 | 6 h | pyramidal | build1 wk 5 | 18.4 % |
| 8 | 6 h | polarized | build1 wk 5 | 18.6 % |

The same 2 seed-3 weeks breach with the planner from `446ba31`, which predates
the injury (#113) and race (#111) hooks, so those hooks are not the cause.

Why the 2026-10-16 count was 1 is **not reproduced**: the planner before
`446ba31` does not import on this tree (the product rename), and that commit
also changed 4,309 workout files, so it was not bisected further.

### Root cause (instrumented)

In all 7 weeks the z5+ minutes come from three `vo2_short` sessions. The
phase's whole `vo2_short` count equals its floor exactly
(`_PHASE_HARD_FLOORS`: build1 4, build2 3), and the floor pass put them in one
week. For the three seed-3 and seed-1 weeks:

| Week | vo2_short before the floor pass | after |
|---|---:|---:|
| 6 h pyramidal seed 3, wk 9 | 1 | 3 |
| 6 h threshold seed 3, wk 10 | 0 | 3 |
| 6 h threshold seed 1, wk 7 | 1 | 3 |

How the two passes combine to produce the breach:

1. **The floor pass concentrates the class.** `_enforce_build2_peak_hard_floor`
   (`src/training_planner.py:9675`) walks the phase weeks in `_week_hit_count`
   order (`:9857`).
   - Every week ties at 3 HIT, so the first week comes first.
   - The swap loop fills the whole deficit there before it moves on. A
     HIT-for-HIT swap is net-neutral, so the FIX-1a weekly cap never stops it.
   - Nothing in the pass looks at the week's z5+ share.
2. **The rail will not shed a floor class.** `_enforce_z5plus_share_ceiling`
   (`:10231`) runs last in every entry point. It sheds only classes above their
   phase floor, and all three sessions sit on it, so the rail does nothing.
   Floor beats rail, which is the order the owner chose on 2026-10-16.

`test_the_ceiling_breach_is_the_floor_pass_concentrating_one_class` reproduces
both seed-3 weeks. It also asserts the before and after counts, that a re-run of
the rail sheds nothing, and that the same week relabelled `base` (no floors) is
brought under the line.

A latent mismatch, with **no measured effect**: the rail compares a class's
count within the week against a per-phase floor. In every measured breach the
phase count equals the floor too, so a per-phase comparison would shield the
same sessions.

### Why it was not fixed here

Both candidate fixes were prototyped outside the committed tree and measured.
Neither is small, local or output-neutral.

| Candidate | Breaches (of 864) | Property-test weeks changed | Golden owner0 / owner1 changed | Other tests |
|---|---:|---:|---|---|
| A. The rail wins: drop the floor shield in `_enforce_z5plus_share_ceiling` | 0 | 7 (only the breaching weeks) | 2 / 1 | breaks `test_planner_variety_bonus.py::TestBuild2PeakPhaseFloors::test_peak_phase_floors` |
| B. Spread the floor: at most one placement per week per round in `_enforce_build2_peak_hard_floor` | 1 (6 h pyramidal seed 3 wk 9, 18.2 %) | 505 | 11 / 12 | not run |

Candidate A in detail:

- **Golden cases that move:** `event/wkend3h/generate-thu` and
  `event/wkend3h/recalculate@21` (owner0), plus `event/wkend3h/recalculate@21`
  (owner1).
- **What moves:** in each, the 2-day stub week's anaerobic or vo2_short session
  becomes z2 (`under_delivery:13` is added).
- **Side effect:** the `expectedFailure` would start passing, but the peak and
  build2 floors are no longer met on the plans it touches.
- **Decision needed:** whether floor or rail wins, which is an owner decision.

Candidate B in detail:

- **Golden cases that move:** every event rider's generate, generate-thu,
  recalculate, refit and reforecast case, plus `ctl/target60/generate` in owner
  mode.
- **Nature of the change:** an intentional algorithm change, with its own
  reviewed before and after.

The real fix is still the one recorded in
code-bloat/planner-audit.md: make the weekly intensity budget a build-time
constraint (`hard_share`, notes/overhaul-plan.md Step 6).

The docstring of the expected failure is stale (it names one week). It was left
alone because that file is outside this change.

## Resolution (2026-10-18): the rail wins

**Decision (owner, #11):** the last-pass weekly intensity ceiling (at most 18 %
of a week's minutes at z5+) overrides a phase's hard-session floor. This is
candidate A, in its narrowest form.

- `_enforce_z5plus_share_ceiling` still sheds classes above their phase floor
  first. Only when no such session is left does it shed a class sitting on its
  floor. A week the old rail could fix is fixed exactly as before.
- `_enforce_build2_peak_hard_floor` is unchanged. It still concentrates the
  floor in one week; the rail then takes one session back out.

**Measured effect:**

- **Property set:** 0 of 864 full weeks breach (was 7). Exactly those 7 weeks
  changed, one `vo2_short` session each, demoted to a real tempo or z2 file.
  The other 857 weeks are identical. The phase then ends one `vo2_short` under
  its floor.
- **Golden:** 3 cases moved, 2 in owner0 and 1 in owner1. All other cases are
  unchanged (builders 49, owner0 77 of 79, owner1 78 of 79).
  - `event/wkend3h/generate-thu` (owner0), week 13, the 2-day stub before the
    taper: its anaerobic session becomes z2.
  - `event/wkend3h/recalculate@21` (owner0 and owner1), week 13: its
    vo2_short session becomes z2.
  - Why: in each case that one session alone put the stub week over the line
    (20.8 % and 25.0 %), and it was a class on its phase floor. Each case gains
    `under_delivery:13`, because the stub now delivers less TSS than its target.
- **Short weeks:** no short week in the 21 invariant cases is over the line
  now. `SHORT_WEEKS_OVER` is gone.
- **Tests:**
  - `test_tid_plan_properties.py::test_no_week_breaches_the_intensity_ceiling`
    is no longer an `expectedFailure`.
  - `test_planner_invariants.py` checks the 864-week set directly (about a
    minute).
  - `test_planner_variety_bonus.py::TestBuild2PeakPhaseFloors::test_peak_phase_floors`
    now checks the floors where the floor pass leaves them. It allows the
    delivered plan to fall short only by sessions shed from a week that was
    over the ceiling. Here, that is the peak's one anaerobic session, in its
    2-day stub week.
  - The continuous floor tests (`test_354_continuous_anaerobic_floor.py`,
    `test_floor_every_start_day.py`) take the same allowance. On a Sunday start,
    week 1 is that one day and the floor's 49-minute anaerobic ride alone is
    19.4 % z5+, so the rail eases it. That plan then carries no anaerobic
    session. No other start day is affected.

Still open: making the weekly intensity budget a build-time constraint
(`hard_share`), so the floor pass stops placing what the rail must then take out.

## 3. TrainingWeek sealing: what "non-strict" means in practice

**In production nothing is ever sealed.**

- `_USE_TRAINING_WEEK` is `False`, so `generate_plan` and
  `regenerate_from_today` never build a `TrainingWeek`, and `seal()`
  (`src/week_plan.py:577`) never runs.
- With the guard armed, none of the 79 cases recorded a post-seal write,
  although the harness itself edits sessions in 37 of them (regenerate,
  refit and the TSB reforecasts). No session in the
  21 test cases carries `_sealed`.
- `_install_seal` (`src/week_plan.py:180`), the only thing that makes a sealed
  session notice a write, is never called from `src/`. Its callers are
  `tests/test_week_plan_owner.py` (a unit test) and
  `tests/probe_owner_vs_legacy.py`.
- So in production the value of `STRICT_SEAL` has no effect at all. No write
  raises, logs or counts.
- The comment at `week_plan.py:174` ("Tests run strict") holds only for that one
  unit test.

**`amend()` is on no path.**

- `TrainingWeek.amend` (`src/week_plan.py:584`) is called only by
  `tests/test_week_plan_owner.py`.
- The rider's edits named as its users (drag, swap type, completion status)
  write to the stored plan dicts in `src/app.py`, for example
  `out["user_moved"] = True` at `:13311` and `s_json["status"] = new_status` at
  `:15684`.
- Sessions are rebuilt from those dicts as fresh, unsealed `PlannedSession`
  objects.
- **No supported amendment path exists in code yet.**

**In owner mode the seal is set, and later passes write through it.** These
writes were measured with the guard armed in audit mode
(`_USE_TRAINING_WEEK = True`, `STRICT_SEAL = False`) over the same 79 cases:

| Entry point | Cases with a post-seal write | Writers (number of writes) |
|---|---|---|
| generate | 24 of 26 | `_enforce_slot_file_coherence` (266) and `_match_zwo_unclamped` (266, called by coherence), after `finish()` sealed the week (`training_planner.py:9314-9318`) |
| regenerate | 16 of 16 | coherence (66) and `_match_zwo_unclamped` (62), after `finish()` (`:14012-14021`) |
| reforecast | 2 of 2 | `reforecast` itself (18), `_match_zwo_unclamped` (4), `_taper_volume_before` (8, B race) |
| refit | 17 of 17 | `_taper_volume_before` (8, B race) |
| injury regenerate | 1 of 1 | coherence (4) and `_match_zwo_unclamped` (4) |
| recalculate, extend | 0 | none |

The table leaves out writes by the harness itself, which stand in for the rider:
`own_some` 96 and `miss_a_hard_day` 21.

There is one more kind of post-seal write the guard cannot detect.
`_enforce_z5plus_share_ceiling` (`training_planner.py:10287`),
`_enforce_weekly_hit_cap` (`:10195`) and `_enforce_slot_file_coherence`
(`:10825`) replace sessions by list assignment (`wk.sessions[i] = new`). The guard sees attribute writes only, so a seal
cannot detect these replacements by construction.

Consequence: turning `STRICT_SEAL` on with the owner on would raise in 24 of
26 generate cases and in every regenerate case. Strictness is unchanged here.
Making it meaningful first needs:

- an amendment path for the app's dict edits;
- coherence moved inside the owner, or run before `finish()`;
- a decision on whether `reforecast` is an owner operation.

## What stays open

- **The intensity ceiling.** Resolved by the rail winning (see Resolution).
  The build-time budget is still open.
- **The enforcement passes are unobserved.** Add a characterization case where
  `_enforce_weekly_hit_cap` and the z5+ rail actually bind. Without one, the
  golden cannot see either pass removed.
- **Regenerate's volume overshoot.** It has the most weekly_volume findings and
  was not root-caused.
- **Refit and stepback weeks.** Refit re-serves a missed hard session into a
  stepback week. This is reproduced only with a harness-made hard session.
- **B race before a stepback (#111).** The B-race taper leaves the following
  stepback heavier than the week it lightened (`stepback_lightest:8`, pinned in
  the tests). Whether that is acceptable is an owner decision.
- **The day-cap check and overrides.** `check_daily_duration_cap` does not read
  per-day overrides.
- **Docs.** REFACTOR-PLAN.md and the former expected failure's docstring were
  refreshed with the Resolution.
