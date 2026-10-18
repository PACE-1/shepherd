# Strength and mobility sessions (#127)

Strength and mobility are **companion sessions** (sport `strength`): the planner places them next to the cycling plan when the rider's saved sport targets give "Other" a share (see `src/multisport_plan.py`). This library (`src/sessions_strength.py`) supplies their content. Browse and print them at `#/strength` (link in Settings); the data is `GET /api/strength/sessions?stage=novice|progressing|experienced`.

**General fitness guidance, not individual medical or coaching advice. Stop if anything hurts (sharp, pinching or joint pain, dizziness) and check with a doctor or qualified coach, especially after an injury or with a health condition.**

## Templates

| id | what | minutes | notes |
|---|---|---|---|
| `strength-general-a` | legs, hips and pull: goblet squat, Romanian deadlift, split squat, one-arm row, glute bridge, plank, calf raise, side plank | 30-45 | a short slot keeps the first 5 exercises |
| `strength-general-b` | single-leg and posterior chain with push: step-up, single-leg RDL, push-up, band row, hip thrust, dead bug, overhead press, Pallof press | 30-45 | |
| `strength-maintenance` | five key lifts, two sets | 20-30 | for heavy training or racing periods |
| `mobility-flexibility` | ten held stretches / mobility moves (2 x 30 s, per side where it applies) | 10-20 | easy; fine on a rest day |

None is a hard session (`hard=False`): the engine may place them on any available day that is not a race day, and they never count against the hard-day budget. Each exercise has sets, reps or a hold time, effort in plain words plus a 0-10 RPE, rest, and a one-line cue. The `workout` dict the engine stores on a companion has effort-only steps (no threshold is needed) plus `exercises`, `stage`, `load_au` and the disclaimer.

## Progression (ACSM 2009)

Source: American College of Sports Medicine position stand, *Progression models in resistance training for healthy adults*, Med Sci Sports Exerc 41(3):687-708.

| stage | sets | reps | session RPE (design) | confidence |
|---|---|---|---|---|
| novice | 1-3 | 8-12 (about 60-70% of 1RM) | 4-6 | the position stand's novice recommendation |
| progressing | 2-4 | 6-10 (about 70-80% of 1RM) | 5-7 | **verify** against the paper |
| experienced | 3-4 | 4-6 (about 80-90% of 1RM) | 6-8 | **verify** against the paper |

The direction (more sets, heavier, fewer repetitions with training experience) is the position stand's; the exact later ranges were written from memory of it and are flagged `verify` in the code, the API and the screen. The stage is the rider's choice on the screen; the plan builder (`builder(thresholds, minutes)` carries no stage) always writes the novice stage into a plan.

Mobility holds follow ACSM 2011 (Garber et al., Med Sci Sports Exerc 43(7):1334-1359): about 10-30 s per hold, 2-4 repetitions. **Verify** the figures; here 2 x 30 s.

**Design choices, not from a source:** the exercise lists and order; five minutes of planning allowance per exercise and two per stretch (`MIN_PER_EXERCISE`, `MIN_PER_STRETCH`); a 5-minute warm-up; plank holds of 20-30 s; the two-set rule for the maintenance session; the session RPE range per stage; the RPE words.

## Load: session-RPE

Foster et al. 2001, *A new approach to monitoring exercise training*, J Strength Cond Res 15(1):109-115: load = session minutes x the rider's 0-10 (CR10) rating of the whole session, taken about 30 minutes after it. `strength_load_au(minutes, rpe)` is that product. It is shown on each session as **arbitrary units (session-RPE), not comparable with TSS**. It is never added to TSS, `multisport.load_by_sport` or the cycling CTL/ATL. The planned figure on a session is a range from the design RPE above, not a measurement; the rider's own rating is what the method uses.

## Where strength shows in the sport-balance card

`sport_balance.balance()` buckets each activity with `multisport.sport_of`, which returns `other` for anything that is not a ride, run or swim. A logged weight-training, yoga or mobility activity therefore adds its **hours** to "Other" (and intervals.icu's own load, if it gives one, to Other's load). The planner's strength share is likewise `other` (`BALANCE_SPORT["strength"]`). No change was needed in `sport_balance.py`.

## Not validated

These are design templates after published sources. They have not been validated with real riders or runners, and the numbers above marked verify have not been read against the papers.
