"""Strength and mobility session library (#127): templates for the companion-session engine
(multisport_plan.register) with exercise lists, sets, reps or hold times, effort words and one-line cues.

Pure: no I/O. Imported by multisport_plan._load_libraries; it registers four templates and retires the
placeholder it replaces.

SOURCES (each number below says which one it comes from)
  * ACSM 2009: American College of Sports Medicine position stand, "Progression models in resistance
    training for healthy adults", Med Sci Sports Exerc 41(3):687-708. Novice: 1-3 sets of 8-12 repetitions
    (the placeholder this replaces already cited it). Later stages use the position stand's "more sets,
    heavier, fewer repetitions with training experience" direction; the exact ranges for them are marked
    VERIFY because they were written from memory of the paper, not read against it.
  * ACSM 2011: Garber et al., "Quantity and quality of exercise for developing and maintaining cardiorespiratory,
    musculoskeletal, and neuromotor fitness", Med Sci Sports Exerc 43(7):1334-1359 (stretch holds of about
    10-30 s, 2-4 repetitions per stretch). VERIFY the exact figures.
  * Foster et al. 2001: "A new approach to monitoring exercise training", J Strength Cond Res 15(1):109-115
    (session-RPE load = session minutes x the rider's CR10 rating of the whole session, arbitrary units).

NOT FROM A SOURCE (design choices, shown as such): which exercises are listed, their order, the five-minutes-
per-exercise planning allowance, the hold seconds of the core exercises, the session RPE ranges per stage,
the two-set maintenance rule. NOT VALIDATED with real riders or runners. General fitness guidance, not
individual medical or coaching advice (``DISCLAIMER``).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import multisport_plan as mp

DISCLAIMER = ("General fitness guidance, not individual medical or coaching advice. Stop if anything hurts "
              "(sharp, pinching or joint pain, dizziness) and check with a doctor or qualified coach, "
              "especially after an injury or if you have a health condition.")
LOAD_NOTE = "arbitrary units (session-RPE), not comparable with TSS"
LOAD_METHOD = ("Session-RPE (Foster et al. 2001, J Strength Cond Res 15(1):109-115): minutes x your 0-10 "
               "rating (CR10) of the whole session, rated about 30 minutes after it.")
NOT_VALIDATED = "Design templates after published sources; not validated with real riders or runners."
ACSM_2009 = ("ACSM position stand, Progression models in resistance training for healthy adults, "
             "Med Sci Sports Exerc 2009;41(3):687-708")
ACSM_2011 = ("Garber et al., ACSM position stand, Quantity and quality of exercise ..., "
             "Med Sci Sports Exerc 2011;43(7):1334-1359")
FOSTER_2001 = "Foster et al., A new approach to monitoring exercise training, J Strength Cond Res 2001;15(1):109-115"
WARMUP_MIN = 5          # design: a warm-up block before the lifts
MIN_PER_EXERCISE = 5    # design planning allowance per rep-based exercise (sets, rest, setup), not from ACSM
MIN_PER_STRETCH = 2     # design: 2 x 30 s hold, per side where it applies, plus moving between stretches


# ── load: session-RPE ──────────────────────────────────────────────────────────────────────────────
def strength_load_au(minutes: float, rpe: float) -> float:
    """Session load in arbitrary units = minutes x session RPE (CR10, 0-10), Foster et al. 2001.

    Not comparable with TSS and never added into TSS or multisport.load_by_sport. Raises ValueError for a
    negative, non-finite or non-numeric minutes, or an rpe outside 0-10."""
    for v, name in ((minutes, "minutes"), (rpe, "rpe")):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise ValueError(f"{name} must be a number")
    if minutes < 0:
        raise ValueError("minutes must be 0 or more")
    if not 0 <= rpe <= 10:
        raise ValueError("rpe must be between 0 and 10 (CR10)")
    return round(float(minutes) * float(rpe), 1)


# ── progression ────────────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Stage:
    """How the same exercise is prescribed as strength training experience grows."""
    id: str
    label: str
    sets: tuple         # (fewest, most) sets per exercise
    reps: tuple         # (fewest, most) repetitions per set
    rpe: tuple          # the rider's effort per hard set, CR10 words below; also the session RPE range (design)
    effort: str         # plain-language load guidance
    rest: str
    pct_1rm: str        # ACSM loading, for riders who know their 1RM
    source: str
    verify: bool        # True: written from memory of the paper, check before relying on it


STAGES: tuple[Stage, ...] = (
    Stage("novice", "Novice (first months)", (1, 3), (8, 12), (4, 6),
          "Moderate: stop each set while you could still do 2-4 more clean repetitions. Add a set or a little "
          "weight only when the top of the rep range feels easy for two sessions in a row.",
          "1-2 minutes between sets", "about 60-70% of 1RM (ACSM 2009, novice)", ACSM_2009 + " (novice)", False),
    Stage("progressing", "Progressing (several months of regular lifting)", (2, 4), (6, 10), (5, 7),
          "Moderately hard: the last 2 repetitions of a set are slow but clean; you could do 1-3 more.",
          "2 minutes between sets", "about 70-80% of 1RM (ACSM 2009, intermediate; VERIFY)",
          ACSM_2009 + " (intermediate; VERIFY ranges)", True),
    Stage("experienced", "Experienced (a year or more of regular lifting)", (3, 4), (4, 6), (6, 8),
          "Hard: heavy but controlled, 1-2 clean repetitions left in the tank; never grind to failure.",
          "2-3 minutes between sets", "about 80-90% of 1RM (ACSM 2009, advanced; VERIFY)",
          ACSM_2009 + " (advanced; VERIFY ranges)", True),
)
STAGE = {s.id: s for s in STAGES}
DEFAULT_STAGE = "novice"
MAINTENANCE_SETS = 2    # design: the short session keeps the stage's reps and effort with two sets (VERIFY vs ACSM)
HOLD_SETS = (1, 3)      # design: holds (planks) use the stage's set count, low end for novices
STRETCH_HOLD_S = 30     # ACSM 2011: 10-30 s per hold, 2-4 repetitions (VERIFY); here 2 x 30 s


# ── exercises ──────────────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Exercise:
    id: str
    name: str
    pattern: str                    # squat | hinge | lunge | push | pull | core | calf | mobility
    cue: str
    per_side: bool = False
    hold_s: int | None = None       # None: counted in repetitions
    reps: tuple | None = None       # fixed repetition range for slow movements that ignore the stage (mobility)


EX = {e.id: e for e in (
    Exercise("goblet-squat", "Goblet squat", "squat", "Hold the weight at your chest, sit down between your hips, drive through the whole foot."),
    Exercise("rdl", "Romanian deadlift", "hinge", "Soft knees, push the hips back, back flat, weight slides down the thighs."),
    Exercise("split-squat", "Split squat", "lunge", "Short stance, torso tall, lower straight down, front heel stays down.", per_side=True),
    Exercise("db-row", "One-arm dumbbell row", "pull", "Flat back, pull the elbow to the hip, pause, lower slowly.", per_side=True),
    Exercise("glute-bridge", "Glute bridge", "hinge", "Ribs down, push through the heels, squeeze at the top, no arching of the lower back."),
    Exercise("calf-raise", "Single-leg calf raise", "calf", "Full range: rise tall on the big toe, pause, lower for 2 seconds.", per_side=True),
    Exercise("plank", "Front plank", "core", "Body in one line from head to heels, ribs down, breathe steadily.", hold_s=30),
    Exercise("side-plank", "Side plank", "core", "Hips lifted and stacked, elbow under shoulder, neck long.", per_side=True, hold_s=20),
    Exercise("step-up", "Step-up", "lunge", "Whole foot on a knee-height box, drive up with the top leg, lower with control.", per_side=True),
    Exercise("sl-rdl", "Single-leg Romanian deadlift", "hinge", "Hinge at the hip with a long back, hips level, touch a light weight toward the floor.", per_side=True),
    Exercise("hip-thrust", "Hip thrust", "hinge", "Upper back on a bench, chin tucked, drive the hips up and pause for a second."),
    Exercise("push-up", "Push-up", "push", "Hands under shoulders, body straight; use a raised surface if you cannot keep the line."),
    Exercise("band-row", "Band or cable row", "pull", "Pull the elbows back and squeeze the shoulder blades, no shrugging."),
    Exercise("oh-press", "Overhead press", "push", "Ribs down, press in a straight line, finish with the biceps by the ears."),
    Exercise("dead-bug", "Dead bug", "core", "Lower back stays on the floor, move the opposite arm and leg slowly.", per_side=True),
    Exercise("pallof", "Pallof press", "core", "Resist the band's pull to rotate; press out, hold a beat, return.", per_side=True),
    # mobility: holds of STRETCH_HOLD_S (ACSM 2011), no load
    Exercise("hip-flexor", "Half-kneeling hip flexor stretch", "mobility", "Tuck the pelvis, squeeze the back glute, lean the hips gently forward.", per_side=True, hold_s=STRETCH_HOLD_S),
    Exercise("hamstring", "Hamstring stretch", "mobility", "Heel on a low step, long back, hinge forward until you feel a pull, not pain.", per_side=True, hold_s=STRETCH_HOLD_S),
    Exercise("figure-four", "Figure-four glute stretch", "mobility", "Ankle over the opposite knee, pull the thigh toward you, relax the shoulders.", per_side=True, hold_s=STRETCH_HOLD_S),
    Exercise("calf-stretch", "Wall calf stretch", "mobility", "Back heel down, back leg straight, lean in until you feel the calf.", per_side=True, hold_s=STRETCH_HOLD_S),
    Exercise("quad-stretch", "Standing quad stretch", "mobility", "Knees together, pull the heel toward the glute, stay tall.", per_side=True, hold_s=STRETCH_HOLD_S),
    Exercise("adductor", "Wide-knee rock back (adductor stretch)", "mobility", "On hands and knees, knees wide, rock the hips back toward the heels.", hold_s=STRETCH_HOLD_S),
    Exercise("open-book", "Open-book thoracic rotation", "mobility", "Lie on your side, knees stacked, open the top arm and follow it with your eyes.", per_side=True, hold_s=STRETCH_HOLD_S),
    Exercise("chest-stretch", "Doorway chest stretch", "mobility", "Forearm on the frame, step through gently, no pinching in the shoulder.", per_side=True, hold_s=STRETCH_HOLD_S),
    Exercise("cat-cow", "Cat-cow", "mobility", "Slow breaths, round then arch the whole spine, small comfortable range.", reps=(8, 10)),
    Exercise("childs-pose", "Child's pose", "mobility", "Sit back onto the heels, arms long, let the breath lengthen the back.", hold_s=STRETCH_HOLD_S),
)}


@dataclass(frozen=True)
class Plan:
    """The design of one session: which exercises, in priority order (a short session keeps the first ones)."""
    id: str
    name: str
    kind: str
    intent: str
    minutes: tuple
    exercises: tuple
    maintenance: bool = False
    mobility: bool = False
    min_exercises: int = 3


PLANS: tuple[Plan, ...] = (
    Plan("strength-general-a", "Strength A: legs, hips and pull", "strength",
         "General strength, lower body and pull: squat, hinge, single-leg work, row and core.", (30, 45),
         ("goblet-squat", "rdl", "split-squat", "db-row", "glute-bridge", "plank", "calf-raise", "side-plank"), min_exercises=5),
    Plan("strength-general-b", "Strength B: single-leg, posterior chain and push", "strength",
         "General strength, single-leg and posterior chain with push and core.", (30, 45),
         ("step-up", "sl-rdl", "push-up", "band-row", "hip-thrust", "dead-bug", "oh-press", "pallof"), min_exercises=5),
    Plan("strength-maintenance", "Strength maintenance (short)", "maintenance",
         "Short session that keeps strength going in a heavy training or racing period: five key lifts, two sets.",
         (20, 30), ("goblet-squat", "rdl", "push-up", "db-row", "plank"), maintenance=True),
    Plan("mobility-flexibility", "Mobility and flexibility", "mobility",
         "Easy stretching and mobility with held positions; fine on a rest day or after an easy ride.", (10, 20),
         ("hip-flexor", "hamstring", "figure-four", "calf-stretch", "quad-stretch", "adductor", "open-book",
          "chest-stretch", "cat-cow", "childs-pose"), mobility=True, min_exercises=4),
)
PLAN = {p.id: p for p in PLANS}


def _stage(stage: str | None) -> Stage:
    try:
        return STAGE[stage or DEFAULT_STAGE]
    except KeyError:
        raise ValueError(f"stage must be one of {', '.join(STAGE)}") from None


def prescribe(ex: Exercise, stage: Stage, maintenance: bool = False) -> dict:
    """One exercise as the rider reads it: sets, reps or hold seconds, effort words, rest and the cue."""
    base = {"id": ex.id, "name": ex.name, "pattern": ex.pattern, "per_side": ex.per_side, "cue": ex.cue}
    if ex.pattern == "mobility":
        return {**base, "sets": [2, 2] if ex.hold_s else [1, 1], "reps": list(ex.reps) if ex.reps else None,
                "hold_s": ex.hold_s, "rpe": [1, 2], "effort": "Easy: a mild stretch, never pain. Breathe out slowly.",
                "rest": "move straight on"}
    sets = (min(stage.sets[1], MAINTENANCE_SETS),) * 2 if maintenance else stage.sets
    if ex.hold_s:
        return {**base, "sets": list(HOLD_SETS if not maintenance else (MAINTENANCE_SETS,) * 2), "reps": None,
                "hold_s": ex.hold_s, "rpe": [3, 5], "effort": "Steady: quality over time; stop the set when your form goes.",
                "rest": "30-60 seconds"}
    return {**base, "sets": list(sets), "reps": list(stage.reps), "hold_s": None, "rpe": list(stage.rpe),
            "effort": stage.effort, "rest": stage.rest}


def _n_exercises(p: Plan, minutes: float) -> int:
    per = MIN_PER_STRETCH if p.mobility else MIN_PER_EXERCISE
    warm = 0 if p.mobility else WARMUP_MIN
    return max(p.min_exercises, min(len(p.exercises), int((minutes - warm) // per)))


def session_rpe_range(p: Plan, stage: Stage) -> tuple:
    """Design RPE range (CR10) of the whole session, for the planned-load display. Not measured."""
    if p.mobility:
        return (1, 2)
    if p.maintenance:
        return (max(stage.rpe[0] - 1, 3), max(stage.rpe[1] - 1, 4))
    return stage.rpe


def build_session(plan_id: str, stage: str | None = None, minutes: int | None = None) -> dict:
    """A full session at a stage: exercise list, planned load range in session-RPE units, notes.

    ``minutes`` defaults to the template's longest session and is clamped into its range."""
    p, st = PLAN[plan_id], _stage(stage)
    lo, hi = p.minutes
    m = hi if minutes is None else max(lo, min(hi, int(minutes)))
    n = _n_exercises(p, m)
    rpe = session_rpe_range(p, st)
    return {
        "id": p.id, "name": p.name, "kind": p.kind, "intent": p.intent, "minutes": m,
        "minutes_range": [lo, hi], "stage": st.id, "stage_label": st.label, "hard": False,
        "exercises": [prescribe(EX[i], st, p.maintenance) for i in p.exercises[:n]],
        "rpe_range": list(rpe), "load_au": [strength_load_au(m, rpe[0]), strength_load_au(m, rpe[1])],
        "load_note": LOAD_NOTE, "load_method": LOAD_METHOD,
        "progression": None if p.mobility else {"sets": list(st.sets), "reps": list(st.reps), "rest": st.rest,
                                                 "pct_1rm": st.pct_1rm, "verify": st.verify},
        "warmup_min": 0 if p.mobility else WARMUP_MIN, "disclaimer": DISCLAIMER, "not_validated": NOT_VALIDATED,
        "source": ACSM_2011 if p.mobility else ACSM_2009,
    }


def _workout(plan_id: str, thresholds: dict, minutes: int) -> dict:
    """The engine's builder: workout_builder-shaped steps (effort targets only, no threshold needed) plus the
    exercise list and planned load. Always novice-stage; the Strength screen shows every stage."""
    s = build_session(plan_id, DEFAULT_STAGE, minutes)
    warm = s["warmup_min"]
    steps = []
    if warm:
        steps.append({"kind": "warmup", "duration_s": warm * 60, "cadence_note": "",
                      "target": {"kind": "effort", "label": "easy, joints warm: bodyweight squats, hip hinges, arm circles"}})
    steps.append({"kind": "work", "duration_s": (s["minutes"] - warm) * 60, "cadence_note": "",
                  "target": {"kind": "effort", "label": "easy, gentle stretch" if s["kind"] == "mobility"
                             else f"moderate, RPE {s['rpe_range'][0]}-{s['rpe_range'][1]} of 10"}})
    return {"name": s["name"], "description": s["intent"], "steps": steps, "exercises": s["exercises"],
            "stage": s["stage"], "load_au": s["load_au"], "load_note": LOAD_NOTE, "disclaimer": DISCLAIMER}


def _register() -> None:
    mp.unregister("placeholder-strength-general")
    for p in PLANS:
        mp.register(mp.SessionTemplate(
            id=p.id, sport="strength", kind=p.kind, session_type="strength", intent=p.intent,
            minutes=p.minutes, hard=False, source=ACSM_2011 if p.mobility else ACSM_2009,
            builder=lambda th, m, _id=p.id: _workout(_id, th, m)))


_register()
