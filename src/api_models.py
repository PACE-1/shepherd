"""Typed response contracts for the endpoints the new UI uses (#10).

Scope is the migrated workflows, not the whole API: profile picker, setup
wizards, intervals.icu connection and the DFA tab. The models are attached to
routes with ``responses={200: {"model": ...}}``, which documents the contract
in OpenAPI WITHOUT validating or filtering live responses, so a value of an
unexpected type can never turn a working endpoint into a 500. Every model also
allows extra keys.

``tests/test_api_contract.py`` compares the generated OpenAPI schema of these
routes with ``tests/api_contract.json``, and ``web/src/api/schema.d.ts`` is
generated from the same schema (``tools/gen-api-types.sh``). A change that
alters a contract therefore fails a test until the snapshot is regenerated on
purpose.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="allow")


class Ok(_Model):
    ok: bool = True


def request_body(model: type[BaseModel]) -> dict:
    """``openapi_extra`` that documents a JSON request body without validating it.

    The handlers still read the raw body and answer their own 400s, so the status
    codes and messages stay as they were. Use flat models: the schema is inlined.
    """
    return {"requestBody": {"required": True, "content": {"application/json": {
        "schema": model.model_json_schema(mode="validation")}}}}


# ── profiles ────────────────────────────────────────────────────────────────
class ProfileEntry(_Model):
    id: str
    name: str = ""
    color: Optional[str] = None
    created: Optional[str] = None
    last_used: Optional[str] = None
    bootstrapped: Optional[bool] = None
    ftp: Optional[float] = None
    weight_kg: Optional[float] = None


class ProfilesList(_Model):
    active: Optional[str] = None
    active_name: Optional[str] = None
    active_color: Optional[str] = None
    profiles: list[ProfileEntry] = []


class ProfileCreated(_Model):
    ok: bool = True
    id: str
    warning: Optional[str] = None


class ProfileSwitched(_Model):
    ok: bool = True
    active: Optional[str] = None


class EnsureProfile(_Model):
    ok: bool = True
    id: str


# ── setup ───────────────────────────────────────────────────────────────────
class SetupDefaults(_Model):
    icu_id: str = ""
    workout_dir: str = ""
    gpx_dir: str = ""
    weight: Optional[float] = None
    ftp: Optional[float] = None
    lthr: Optional[float] = None
    max_hr: Optional[float] = None


class IcuConnection(_Model):
    connected: bool = False
    method: str = "none"          # "oauth" | "apikey" | "none"
    athlete_id: str = ""
    name: str = ""
    write_ok: bool = False
    needs_oauth_migration: bool = False
    oauth_available: bool = False


class SyncProgress(_Model):
    state: Optional[str] = None   # idle | running | done | stale
    total: Optional[int] = None
    done: Optional[int] = None
    added: Optional[int] = None
    updated: Optional[int] = None
    ts: Optional[float] = None


# ── DFA α1 ──────────────────────────────────────────────────────────────────
class DfaThreshold(_Model):
    hr: Optional[float] = None
    power: Optional[float] = None
    r2_hr: Optional[float] = None
    r2_power: Optional[float] = None
    r2_hr_median: Optional[float] = None
    r2_power_median: Optional[float] = None
    n_hr: Optional[int] = None
    n_power: Optional[int] = None
    date_span: Optional[list[str]] = None


class DfaZoneMinutes(_Model):
    z1: float = 0
    z2: float = 0
    z3: float = 0


class DfaRide(_Model):
    id: str
    date: Optional[str] = None
    name: Optional[str] = None
    duration_min: Optional[float] = None
    avg_hr: Optional[float] = None
    alpha1_avg: Optional[float] = None
    lt1_minutes: Optional[float] = None
    status: Optional[str] = None
    zone_minutes: Optional[DfaZoneMinutes] = None
    hrvt1: Optional[DfaThreshold] = None
    hrvt1_note: Optional[str] = None
    hrvt2: Optional[DfaThreshold] = None
    hrvt2_note: Optional[str] = None
    algo_version: Optional[int] = None


class DfaAggregate(_Model):
    hrvt1: Optional[DfaThreshold] = None
    hrvt2: Optional[DfaThreshold] = None
    n_window: Optional[int] = None
    agg_min_r2: Optional[float] = None
    agg_max_decoupling: Optional[float] = None
    n_excluded_decoupling: Optional[int] = None


class DfaRides(_Model):
    rides: list[DfaRide] = []
    aggregate: DfaAggregate = DfaAggregate()
    n_total: int = 0
    n_computed: int = 0
    n_stale_version: int = 0


class BackfillStarted(_Model):
    status: str                   # "started" | "already_running"
    task_id: Optional[str] = None


class BackfillStatus(_Model):
    task_id: Optional[str] = None
    state: Optional[str] = None   # running | done | cancelled | error
    augmented: Optional[int] = None
    candidates: Optional[int] = None
    computed: Optional[int] = None
    no_rr_data: Optional[int] = None
    icu_deleted: Optional[int] = None
    failed: Optional[int] = None
    current: Optional[str] = None


# ── plan and Home reads (#10) ───────────────────────────────────────────────
# The plan models mirror the planner's own codec (``session_to_dict`` /
# ``week_to_dict`` / ``goal_to_dict``); ``tests/test_api_models_plan.py`` fails if
# a dataclass field is added without being declared here.
class PlanSession(_Model):
    day: str
    day_name: str = ""
    session_type: str
    duration_min: int = 0
    tss_estimate: float = 0
    description: str = ""
    zwo_file: str = ""
    zwo_name: str = ""
    nutrition_note: str = ""
    matched: bool = True
    adapted: bool = False
    status: str = "pending"
    user_moved: bool = False
    moved_from: str = ""
    user_swapped: bool = False
    completion_matches: Optional[list] = None
    dismissed_at: str = ""
    wprime_estimate: Optional[float] = None
    pmax_estimate: Optional[float] = None
    hr_ceiling_pct: Optional[float] = None
    is_double_threshold_pair: bool = False
    double_threshold_partner_id: Optional[str] = None
    am_or_pm: Optional[str] = None
    is_race: bool = False
    race: Optional[dict] = None
    is_opener: bool = False
    execution: Optional[dict] = None


class PlanWeek(_Model):
    week_num: int
    start: str
    end: str
    phase: str = ""
    tss_target: float = 0
    is_stepback: bool = False
    sessions: list[PlanSession] = []


class PlanPhase(_Model):
    name: str
    weeks: int = 0
    start: str = ""
    end: str = ""
    weekly_tss: Optional[float] = None
    focus: str = ""


class PlanGoal(_Model):
    type: str = ""
    event_date: Optional[str] = None
    event_name: str = ""
    hours_per_week: Optional[float] = None
    plan_weeks: Optional[int] = None
    start_date: Optional[str] = None
    entry_mode: Optional[str] = None
    focus: str = ""


class PlanJson(_Model):
    goal: PlanGoal = PlanGoal()
    phases: list[PlanPhase] = []
    weeks: list[PlanWeek] = []
    generated: Optional[str] = None
    ctl_snapshot: Optional[dict] = None
    ctl_drift: Optional[dict] = None     # {exceeded, snapshot_ctl, live_ctl, generated_on}: the plan assumes a different fitness than you have
    availability: Optional[dict] = None


class PlanRead(_Model):
    plan_json: PlanJson
    plan: str = ""
    file: str = ""


class ProgrammeSummary(_Model):
    plan_id: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    weeks: int = 0
    rides: int = 0
    ftp_delta: Optional[dict] = None
    eftp_delta: Optional[dict] = None
    vo2max_delta: Optional[dict] = None
    ctl_gain: Optional[dict] = None
    intensity_dist: Optional[dict] = None
    pol_index: Optional[dict] = None
    compliance: list[dict] = []
    totals: Optional[dict] = None
    citations: list[str] = []


class RiderStats(_Model):
    errors: list[str] = []
    power: Optional[dict] = None
    peaks: Optional[dict] = None
    heart: Optional[dict] = None
    efficiency: Optional[dict] = None
    load: Optional[dict] = None
    body: Optional[dict] = None
    season: Optional[dict] = None


class DismissSessionBody(_Model):
    date: str                            # YYYY-MM-DD; every session on that date
    undo: bool = False                   # true restores a dismissed session


class MoveSessionBody(_Model):
    date: str
    new_date: str


class SwapTypeBody(_Model):
    date: str
    session_type: str
    duration_min: int


class FtpTestTypeBody(_Model):
    date: str
    test_type: str                       # ramp | coggan_20min | sixty_min | cp_test


class SessionDismissed(_Model):
    ok: bool = True
    dismissed: bool


class SessionMoved(_Model):
    ok: bool = True
    moved: Optional[PlanSession] = None
    vacated: Optional[str] = None      # date the move left empty, if any
    swapped: Optional[PlanSession] = None   # the session now on the source date, on a swap


class SessionSwapped(_Model):
    ok: bool = True
    day: str
    session_type: str
    duration_min: int = 0
    tss_estimate: float = 0
    zwo_file: str = ""
    zwo_name: str = ""
    sessions_modified: Optional[int] = None   # later sessions the reforecast rebalanced


class UnavailablePeriod(_Model):
    start: str
    end: str
    type: str = "holiday"
    daily_tss: float = 0
    reason: str = ""


class UnavailableMarked(_Model):
    ok: bool = True
    period: UnavailablePeriod
    plan_json: Optional[PlanJson] = None


class PlanRegenerated(_Model):
    ok: bool = True
    plan_json: Optional[PlanJson] = None
    regen_info: Optional[dict] = None


# ── Plan tools: availability, races, FTP-test type, rematch, redraw, deload ──

class AvailabilitySaved(_Model):
    ok: bool = True
    sessions_modified: int = 0


class RaceAdded(_Model):
    ok: bool = True
    plan_json: Optional[PlanJson] = None
    regen_info: Optional[dict] = None
    added: Optional[dict] = None


class FtpTestTypeSet(_Model):
    ok: bool = True
    test_type: str
    zwo_file: str = ""
    zwo_name: str = ""
    duration_min: Optional[int] = None
    tss_estimate: Optional[float] = None
    display_name: Optional[str] = None


class RematchResult(_Model):
    """Preview (apply=0) or result (apply=1). `action` is set when there is no current week."""
    ok: Optional[bool] = None
    apply: Optional[bool] = None
    action: Optional[str] = None
    changed: Optional[int] = None


class RedrawCandidate(_Model):
    ok: bool = True
    action: Optional[str] = None       # "no_candidate" / "invalid" when ok is false
    day: str = ""
    reason: Optional[str] = None
    session_type: Optional[str] = None
    zwo_file: Optional[str] = None
    zwo_name: Optional[str] = None
    variation: Optional[int] = None
    duration_min: Optional[int] = None
    tss_estimate: Optional[float] = None
    exhausted: Optional[bool] = None


class RedrawAccepted(_Model):
    ok: bool = True
    day: str = ""
    sessions_modified: int = 0


class DeloadReverted(_Model):
    reverted: bool
    reason: Optional[str] = None
    week_num: Optional[int] = None


# ── Today: readiness, adapted session, daily log ────────────────────────────

class ReadinessAdvice(_Model):
    advice: str = ""


class Readiness(_Model):
    score_0_100: Optional[float] = None
    severity: str = "normal"           # normal | tier_down | rest
    source: Optional[str] = None
    severity_reasons: list[str] = []
    readiness: Optional[ReadinessAdvice] = None
    dfa_cap_applied: Optional[bool] = None
    decoupling_advisory: Optional[bool] = None


class TodaySessionPlan(_Model):
    session_type: str
    duration_min: int = 0
    tss_estimate: float = 0
    description: str = ""
    zwo_name: Optional[str] = None


class TodaySession(_Model):
    planned: Optional[TodaySessionPlan] = None
    adjusted: Optional[TodaySessionPlan] = None
    reason: str = ""
    adjustment_reason: Optional[str] = None
    was_modified: bool = False
    has_plan: Optional[bool] = None
    is_race: bool = False
    retest_nudge: Optional[dict] = None   # {metric, reason, days_since, action, suggested_date, snooze_days}


class TodayPersisted(_Model):
    ok: bool = True
    day: str
    adapted_reason: str = ""
    session_type: str


class CapReverted(_Model):
    ok: bool = True
    reverted: bool = True
    restored: Optional[dict] = None


class TierDownApplied(_Model):
    ok: bool = True
    action: Optional[str] = None       # why nothing changed, when ok is false
    day: str = ""
    old_type: Optional[str] = None
    new_type: Optional[str] = None
    old_tss: Optional[float] = None
    new_tss: Optional[float] = None
    duration_min: Optional[int] = None
    zwo_name: Optional[str] = None


class AutoAdjustResult(_Model):
    ok: bool = True
    severity: str = "normal"
    scope: str = "today"
    dry_run: bool = False
    actions: list[dict] = []
    applied: Optional[bool] = None
    sessions_modified: int = 0
    note: str = ""


class DailyLogEntry(_Model):
    date: str
    sleep_quality: Optional[int] = None
    fatigue: Optional[int] = None
    soreness: Optional[int] = None
    stress: Optional[int] = None
    mood: Optional[int] = None
    notes: Optional[str] = None
    hooper_index: Optional[int] = None
    readiness_to_train: Optional[int] = None


class DailyLogRead(_Model):
    today: Optional[DailyLogEntry] = None
    history: list[DailyLogEntry] = []


class DailyLogSaved(_Model):
    ok: bool = True
    entry: DailyLogEntry


# ── Workout library and picker ──────────────────────────────────────────────

class WorkoutRow(_Model):
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    name: str = Field("", alias="Name")
    category: str = Field("", alias="Category")
    file: str = Field("", alias="File")
    duration_min: float = Field(0, alias="Duration(min)")
    tss: float = Field(0, alias="TSS")
    intensity_factor: float = Field(0, alias="IF")
    score: Optional[float] = Field(None, alias="Score")
    protocol: Optional[str] = Field(None, alias="Protocol")
    tags: list[str] = Field(default_factory=list, alias="Tags")
    content_class: Optional[str] = None
    display_name: Optional[str] = None


class WorkoutSegment(_Model):
    type: str
    start: float = 0
    duration: float = 0
    power: Optional[float] = None
    pct: Optional[float] = None


class WorkoutDetail(_Model):
    name: str = ""
    display_name: Optional[str] = None
    description: str = ""
    total_seconds: int = 0
    segments: list[WorkoutSegment] = []
    ftp: Optional[float] = None
    hr_available: bool = False


class PickerResult(_Model):
    type: str = "z2"
    readiness: Optional[float] = None
    status: str = ""
    advice: str = ""
    baseline_used: Optional[bool] = None
    workouts: list[WorkoutRow] = []


# ── Analysis: fitness and form, power curve, rides ──────────────────────────

class WellnessDay(_Model):
    date: str
    ctl: Optional[float] = None
    atl: Optional[float] = None
    tsb: Optional[float] = None
    hrv: Optional[float] = None
    rhr: Optional[float] = None
    sleep_h: Optional[float] = None
    eftp: Optional[float] = None
    cp_fitness: Optional[float] = None
    w_prime_fitness: Optional[float] = None
    pmax_fitness: Optional[float] = None


class PowerCurvePoint(_Model):
    duration_s: int
    watts: float
    watts_per_kg: Optional[float] = None
    pct_ftp: Optional[float] = None
    ride_id: Optional[str] = None
    date: Optional[str] = None


class PowerBaselinePoint(_Model):
    duration_s: int
    watts_per_kg: float = 0
    watts_at_current_weight: float = 0


class PowerCurve(_Model):
    window_days: int
    n_rides: int = 0
    weight_kg: Optional[float] = None
    current_ftp: Optional[float] = None
    rider_curve: list[PowerCurvePoint] = []
    pg_2011_baseline: list[PowerBaselinePoint] = []
    cp_w: Optional[float] = None
    wprime_j: Optional[float] = None
    pmax_w: Optional[float] = None
    needs_backfill: Optional[bool] = None


class RideSummary(_Model):
    ride_id: str
    source: str = ""
    name: str = ""
    sport: Optional[str] = None
    started_at: Optional[str] = None
    duration_s: Optional[int] = None
    distance_km: Optional[float] = None
    elevation_m: Optional[int] = None
    avg_power_w: Optional[int] = None
    np_w: Optional[int] = None
    tss: Optional[float] = None


# ── Settings, sync and version ──────────────────────────────────────────────

class ZoneBand(_Model):
    zone: str
    name: str = ""
    low: float = 0
    high: float = 0


class SettingsRead(_Model):
    weight: float
    ftp: float
    eftp: Optional[float] = None
    lthr: float
    max_hr: float
    target_mode: str = "power"          # power | hr
    lthr_is_set: bool = False
    w_per_kg: Optional[float] = None
    ftp_source: Optional[str] = None
    ftp_source_date: Optional[str] = None
    lthr_source: Optional[str] = None
    power_zones: list[ZoneBand] = []
    hr_zones: list[ZoneBand] = []


class SettingsSaved(_Model):
    ok: bool = True
    updated: dict = {}
    settings: SettingsRead


class SyncStatus(_Model):
    last_sync: Optional[dict] = None
    wellness_records: int = 0
    activity_records: int = 0
    auth_disabled: bool = False
    consecutive_failures: int = 0
    last_error: Optional[str] = None


class VersionInfo(_Model):
    app: str
    version: str
    python: str = ""
    frozen: bool = False
    data_dir: str = ""


class UpdateCheck(_Model):
    current: str
    latest: Optional[str] = None
    update_available: bool = False
    release_url: Optional[str] = None
    download_url: Optional[str] = None
    checked_at: Optional[str] = None
    error: Optional[str] = None


# ── Rides: import, detail, rpe, ftp test ────────────────────────────────────

class RideImported(_Model):
    ride_id: str
    bytes: int = 0
    parsed_stats: dict = {}
    icu_upload: dict = {}              # {ok, skipped, needs_reconnect, detail}


class RideDetail(RideSummary):
    moving_s: Optional[int] = None
    if_pct: Optional[float] = None
    kj: Optional[float] = None
    kcal: Optional[int] = None
    avg_hr: Optional[int] = None
    hr_max: Optional[int] = None
    avg_cadence: Optional[int] = None
    ftp_at_ride: Optional[float] = None
    decoupling_pct: Optional[float] = None
    dfa_alpha1: Optional[float] = None
    rpe: Optional[int] = None
    is_race: Optional[bool] = None
    activity_id: Optional[str] = None     # key of the race flag; None when the ride has no activity row
    time_in_zone: Optional[dict] = None   # {"z1": seconds, … "z7"}
    hr_time_in_zone: Optional[dict] = None  # same shape, by heart-rate zone; None when the activity has no HR zones
    intervals: list[dict] = []
    efforts: list[dict] = []
    prs: list[dict] = []
    samples: Optional[dict] = None     # with ?include=samples: {t_s, power_w, hr_bpm, cadence_rpm, elevation_m}


class RideRpeSaved(_Model):
    ok: bool = True
    ride_id: str
    rpe: Optional[int] = None
    scale: Optional[str] = None


class RidePrs(_Model):
    ride_id: str
    prs: list[dict] = []


class FtpTestAnalysis(_Model):
    ok: bool = True
    ride_id: str
    source: Optional[str] = None
    suggestion: dict = {}              # {ftp, method, window_start_s, window_end_s, ...}
    halted: bool = False
    total_s: int = 0
    step_s: int = 1
    series: list[int] = []
    windows: list[dict] = []
    prior_ftp: Optional[float] = None


class FtpReviewSaved(_Model):
    ok: bool = True
    persisted: bool = False


class FtpUpdated(_Model):
    ok: bool = True
    ftp: float
    ftp_source: Optional[str] = None
    ftp_test_history: list[dict] = []


class RidesSynced(_Model):
    added: int = 0
    total: int = 0
    skipped: Optional[str] = None
    plan_load_alert: Optional[bool] = None
    plan_adapted: Optional[str] = None


class PrToastQueue(_Model):
    queue: list[dict] = []
    count: int = 0


# ── Wellness, notices, history ──────────────────────────────────────────────

class HrvSaved(_Model):
    ok: bool = True
    date: str
    hrv_manual_rmssd: float


class HrvImported(_Model):
    imported: int = 0
    skipped: int = 0


class HrvPromptStatus(_Model):
    should_show_prompt: bool = False
    device_product_name: Optional[str] = None
    last_ride_id: Optional[str] = None
    dismissal_state: str = "none"       # none | version | permanent
    version: str = ""


class HrvPromptDismissed(_Model):
    ok: bool = True
    level: str
    version: str = ""


class RetestSnoozed(_Model):
    ok: bool = True
    until: Optional[str] = None


class MetricPoint(_Model):
    date: str
    value: float
    source: Optional[str] = None
    notes: Optional[str] = None


class FtpHistoryEntry(_Model):
    date: Optional[str] = None
    ftp: Optional[float] = None
    type: str = "manual"
    source: str = ""
    applied: bool = False
    method: str = "manual"


class FtpHistory(_Model):
    ftp_current: float
    ftp_source: Optional[str] = None
    history: list[FtpHistoryEntry] = []


class SportLoadLine(_Model):
    ctl: float
    atl: float
    tsb: float
    week_load: float


class SportsLoad(_Model):
    as_of: str
    days_of_history: int
    settled: bool
    combined: SportLoadLine
    sports: dict[str, SportLoadLine] = {}
    method: str
    confidence: str


class SportThresholdEntry(_Model):
    value: float
    date: str
    source: str = "manual"


class SportThreshold(_Model):
    sport: str
    unit: str
    current: Optional[float] = None
    history: list[SportThresholdEntry] = []


class SportThresholds(_Model):
    thresholds: dict[str, SportThreshold]


class EventProjection(_Model):
    available: bool
    reason: Optional[str] = None        # why not available
    event_name: Optional[str] = None
    event_date: Optional[str] = None
    event_km: Optional[float] = None
    event_climb_m: Optional[float] = None
    predicted_finish_h: Optional[float] = None
    predicted_np: Optional[float] = None
    predicted_tss: Optional[float] = None
    ftp: Optional[float] = None
    weight_kg: Optional[float] = None
    current_ctl: Optional[float] = None
    gap_endurance_h: Optional[float] = None
    longest_required_h: Optional[float] = None
    longest_completed_ride_h: Optional[float] = None
    gap_power_w_per_kg: Optional[float] = None
    climb_readiness_pct: Optional[float] = None


class Fitness3dStatus(_Model):
    rides_with_ss: int = 0
    rides_total_post_v106: int = 0


class Backfill3d(_Model):
    backfilled: int = 0
    skipped: int = 0
    failed: int = 0
    results: list[dict] = []


class MigrationResult(_Model):
    show_toast: bool = False
    from_version: Optional[str] = None
    to_version: Optional[str] = None
    rider_data_preserved: Optional[bool] = None


# ── Settings: intervals.icu push, folders, zones, logs, diagnostics, history backfill ──

class IcuPushStatus(_Model):
    connected: bool = False
    method: str = "none"
    write_ok: bool = False
    sync_enabled: bool = False
    horizon_days: int = 14
    last_result: Optional[dict] = None


class IcuPushResult(_Model):
    ok: bool = False
    error: Optional[str] = None
    needs_reconnect: Optional[bool] = None
    sync_enabled: Optional[bool] = None
    pushed: Optional[int] = None
    updated: Optional[int] = None
    deleted: Optional[int] = None


class FolderCount(_Model):
    count: int = 0


class ExtraFolder(_Model):
    path: str
    files: int = 0
    added: int = 0


class WorkoutFolders(_Model):
    builtin: FolderCount
    extra: Optional[ExtraFolder] = None


class ZonesSaved(_Model):
    ok: bool = True
    reset: Optional[bool] = None
    zones: Optional[list[ZoneBand]] = None


class LogTail(_Model):
    lines: list[str] = []
    total: int = 0
    path: str = ""
    size_kb: Optional[float] = None
    exists: bool = False


class DiagErrors(_Model):
    count: int = 0
    items: list[dict] = []


class DiagHealth(_Model):
    ok: bool = False
    checks: dict = {}


class BackfillHistoryStarted(_Model):
    status: str                         # started | already_running
    task_id: Optional[str] = None


class BackfillHistoryStatus(_Model):
    task_id: Optional[str] = None
    state: str = "running"             # running | done | error
    backfilled: int = 0
    already_cached: int = 0
    failed: int = 0
    done: Optional[int] = None
    total: Optional[int] = None


# ── Plan: calendar, preview, ride scan, update, races, workout push ─────────

class CalendarPlanned(_Model):
    session_type: str = "rest"
    name: str = ""
    display_name: str = ""
    duration_min: float = 0
    tss: float = 0
    zwo_file: str = ""
    status: str = "pending"
    user_moved: bool = False
    is_race: bool = False


class CalendarDay(_Model):
    date: str
    dow: int = 0
    is_today: bool = False
    planned: Optional[CalendarPlanned] = None
    actual: Optional[dict] = None
    card_state: str = ""
    race: Optional[dict] = None
    availability_hours: Optional[float] = None


class CalendarWeek(_Model):
    iso_year: int
    iso_week: int
    start_date: str
    end_date: str
    phase: Optional[str] = None
    is_stepback: bool = False
    is_current: bool = False
    planned_tss: Optional[float] = None
    actual_tss: Optional[float] = None
    completion_pct: Optional[float] = None
    days: list[CalendarDay] = []


class CalendarRead(_Model):
    today: str
    current_iso_week: Optional[dict] = None
    weeks: list[CalendarWeek] = []
    summary: dict = {}
    goal: Optional[dict] = None
    error: Optional[str] = None


class PreviewPhase(_Model):
    name: str
    weeks: int
    start: str = ""
    end: str = ""
    weekly_tss: Optional[float] = None
    focus: str = ""


class PlanPreview(_Model):
    ok: bool = True
    plan_weeks: int = 0
    goal: str = ""
    event_date: Optional[str] = None
    start_date: Optional[str] = None
    phase_weeks_status: Optional[str] = None
    phase_weeks_rec: Optional[dict] = None
    phase_weeks_disabled_reason: Optional[str] = None
    phases: list[PreviewPhase] = []


class EntryScan(_Model):
    proposal_weeks: int = 0
    equivalent_start_date: Optional[str] = None
    entry_week: Optional[int] = None
    weeks_remaining: Optional[int] = None
    plan_weeks: int = 0
    plan_end_date: Optional[str] = None
    capped: Optional[bool] = None
    weeks: list[dict] = []


class IcuRaces(_Model):
    races: list[dict] = []
    error: Optional[str] = None
    needs_reconnect: Optional[bool] = None


class WorkoutPushed(_Model):
    ok: Optional[bool] = None
    error: Optional[str] = None
    needs_reconnect: Optional[bool] = None
    needs_lthr: Optional[bool] = None


class PlanUpdated(_Model):
    ok: bool = True
    action: Optional[str] = None
    status_message: str = ""
    plan_json: Optional[PlanJson] = None


class PlanReforecasted(_Model):
    ok: bool = True
    plan_json: Optional[PlanJson] = None
    gaps: Optional[dict] = None
    sessions_changed: Optional[int] = None
    reforecast: Optional[dict] = None


class DailyAdapt(_Model):
    action: Optional[str] = None
    projection_only: bool = True
    projected_adaptations: list[dict] = []



class TauFits(_Model):
    fit_status: str = "insufficient_data"   # success | low_confidence | insufficient_data
    n_markers: int = 0
    weighted_n: float = 0
    ctl_tau_fit: Optional[float] = None
    atl_tau_fit: Optional[float] = None
    ctl_tau_ci_low: Optional[float] = None
    ctl_tau_ci_high: Optional[float] = None
    atl_tau_ci_low: Optional[float] = None
    atl_tau_ci_high: Optional[float] = None
    fit_residual_r2: Optional[float] = None
    conventional: Optional[dict] = None


class BanisterValidation(_Model):
    fit_status: str = "insufficient_data"
    comparison: Optional[str] = None        # better_than_literature | in_line | worse_than_literature
    tau_fits_used: Optional[dict] = None
    n_markers_in_holdout: Optional[int] = None
    holdout_weeks: Optional[int] = None
    horizon_weeks: Optional[int] = None
    ftp_mae_w: Optional[float] = None
    ftp_mae_pct: Optional[float] = None
    ftp_mae_pct_ci_low: Optional[float] = None
    ftp_mae_pct_ci_high: Optional[float] = None
    ctl_mae_tss: Optional[float] = None
    ctl_mae_tss_ci_low: Optional[float] = None
    ctl_mae_tss_ci_high: Optional[float] = None


class FatigueResistance(_Model):
    fit_status: str = "insufficient_data"
    reason: Optional[str] = None
    kj_threshold: Optional[int] = None
    n_long_rides: Optional[int] = None
    n_long_rides_with_streams: Optional[int] = None
    robustness_score: Optional[float] = None
    by_duration: list[dict] = []
    scatter: list[dict] = []


class WorkoutTags(_Model):
    tags: list[str] = []


class WeekSummary(_Model):
    week_start: str
    week_end: str
    today: Optional[str] = None
    tss_target: Optional[float] = None       # None: no plan on record for that week
    tss_done: float = 0
    tss_adherence_pct: Optional[float] = None
    duration_min_done: int = 0
    duration_min_planned: int = 0
    exposure_minutes: dict = {}              # low_aerobic, mid_aerobic, high_aerobic, anaerobic
    exposure_minutes_planned: dict = {}
    unclassified_minutes: int = 0
    sports: dict = {}                        # sport -> count of activities
    missed_sessions: list[dict] = []
    planned_days_total: Optional[int] = None
    planned_days_done: Optional[int] = None
    planned_days_missed: Optional[int] = None
    overreach: bool = False
    overreach_reasons: list[str] = []
    week_offset: int = 0


class PlanAutoRecalc(_Model):
    action: str                          # fresh | recalculated | no_change | no_plan
    days_since_recalc: Optional[int] = None
    weeks_regenerated: Optional[int] = None
    plan_json: Optional[PlanJson] = None


class DfaSnapshot(_Model):
    value: Optional[float] = None            # None when no ride has a computed value yet
    n_rides: int = 0
    last_computed_at: Optional[str] = None
    n_recent_total: int = 0
    n_no_rr_data: int = 0
    n_fetch_failed: int = 0
    message: str = ""


class LlmConnection(_Model):
    configured: bool = False
    provider: str = ""
    base_url: str = ""
    model: str = ""
    has_key: bool = False             # the key itself is never returned


class Insight(_Model):
    text: str
    model: str = ""


# ── Notifications (#131) ─────────────────────────────────────────────────────

class NotificationItem(_Model):
    id: int
    event: str                        # readiness | missed | sync_failure
    day: str
    title: str
    body: str
    ts: str
    read: bool = False


class NotificationList(_Model):
    items: list[NotificationItem] = []
    unread: int = 0


class NotificationEvents(_Model):
    readiness: bool = True
    missed: bool = True
    sync_failure: bool = True
    gear_due: bool = True


class NotificationSettings(_Model):
    has_url: bool = False             # the URL itself is never returned
    events: NotificationEvents = NotificationEvents()
    readiness_time: str = ""          # HH:MM, or "" for the first sync of the day


class NotificationTest(_Model):
    ok: bool
    error: str = ""
# ── Workout builder (#110, cycling slice) ────────────────────────────────────
class BuilderProblem(_Model):
    path: str = ""
    message: str = ""


class BuilderPoint(_Model):
    x: float
    y: float


class BuilderPreview(_Model):
    ok: bool = False
    errors: list[BuilderProblem] = []
    warnings: list[str] = []
    duration_s: int = 0
    intensity_factor: Optional[float] = None
    tss: Optional[float] = None
    profile: list[BuilderPoint] = []


class BuilderPush(_Model):
    ok: Optional[bool] = None
    pushed: Optional[int] = None
    event_date: Optional[str] = None
    error: Optional[str] = None
    needs_reconnect: Optional[bool] = None
    needs_lthr: Optional[bool] = None


class BuilderSaved(_Model):
    ok: bool = True
    file: str
    created: bool = True
    push: Optional[BuilderPush] = None      # only on /send


class BuilderLoaded(_Model):
    ok: bool = True
    file: str
    workout: dict
# ── running zones, critical speed, GAP, per-run load (#118, #119; routes_run.py) ──
class RunPaceZone(_Model):
    zone: str
    name: str
    slow_pct: Optional[float] = None
    fast_pct: Optional[float] = None
    slow_s_per_km: Optional[float] = None
    fast_s_per_km: Optional[float] = None


class RunHrZone(_Model):
    zone: str
    name: str
    low_pct: Optional[float] = None
    high_pct: Optional[float] = None
    low_bpm: Optional[int] = None
    high_bpm: Optional[int] = None


class RunZones(_Model):
    threshold_pace_s_per_km: Optional[float] = None
    threshold_hr: Optional[float] = None
    pace_zones: list[RunPaceZone] = []
    hr_zones: list[RunHrZone] = []
    pace_history: list[SportThresholdEntry] = []
    method: str
    confidence: str


class CriticalSpeed(_Model):
    cs_m_per_s: float
    cs_pace_s_per_km: float
    d_prime_m: float
    r2: Optional[float] = None
    n_trials: int
    warnings: list[str] = []
    method: str
    confidence: str
    saved: bool = False


class RunGap(_Model):
    pace_s_per_km: float
    grade_pct: float
    gap_s_per_km: float
    cost_j_per_kg_m: float
    flat_cost_j_per_kg_m: float
    method: str
    confidence: str


class RunActivity(_Model):
    id: str
    date: Optional[str] = None
    name: str = ""
    type: str = ""
    duration_s: float = 0
    distance_km: Optional[float] = None
    pace_s_per_km: Optional[float] = None
    avg_hr: Optional[float] = None
    icu_load: Optional[float] = None
    intensity: Optional[float] = None
    rtss: Optional[float] = None
    hrtss: Optional[float] = None
    cadence_spm: Optional[float] = None
    cadence_doubled: bool = False
    step_length_m: Optional[float] = None
    stride_length_m: Optional[float] = None


class RunActivities(_Model):
    threshold_pace_s_per_km: Optional[float] = None
    threshold_hr: Optional[float] = None
    rest_hr: Optional[float] = None
    max_hr: Optional[float] = None
    max_hr_source: Optional[str] = None
    sex: Optional[str] = None
    runs: list[RunActivity] = []
    missing: list[str] = []
    method: str
    confidence: str
# ── #113 injury and illness (routes_injury.py) ──────────────────────────────

class InjuryEpisode(_Model):
    id: str
    type: str                            # injury | illness
    start: str
    end: Optional[str] = None            # None while the episode is open
    sport: str = "all"                   # all | cycling | running | swimming | other
    body_area: str = ""
    note: str = ""


class InjuryReturn(_Model):
    episode_id: str
    type: str
    start: str
    end: str
    episode_days: int
    absence_days: int                    # what sizes the planner's ramp (at least 7)
    weeks_done: int                      # ramp weeks already behind the rider


class InjuryRampWeek(_Model):
    start: str
    end: str
    phase: str                           # recon (easy only) | recovery_ramp
    tss_target: float = 0
    easy_only: bool = False


class InjuryShortBreak(_Model):
    type: str
    episode_days: int
    end: str


class InjuryStatus(_Model):
    episodes: list[InjuryEpisode] = []
    active: Optional[InjuryEpisode] = None
    return_ramp: Optional[InjuryReturn] = None
    short_break: Optional[InjuryShortBreak] = None   # a finished illness too short for a ramp
    ramp_weeks: list[InjuryRampWeek] = []
    has_plan: bool = False
    plan_synced: bool = False            # the plan's time off changed: rebuild it
    method: str
    note: str


class RampRateLine(_Model):
    week_load: float
    prev_4wk_avg: float
    ratio: Optional[float] = None
    change_pct: Optional[int] = None
    level: str                           # ok | elevated | high | no_base


class RampRate(_Model):
    as_of: str
    threshold: float
    high: float
    combined: RampRateLine
    sports: dict[str, RampRateLine] = {}
    warn: bool
    warnings: list[str] = []
    method: str
    confidence: str
    note: str
# ── analytics: weight trend, power-duration model, ride comparison (#114, #116) ──
class WeightPoint(_Model):
    date: str
    weight_kg: float
    source: str = "manual"
    trend_kg: float


class WkgPoint(_Model):
    date: str
    ftp_w: int
    weight_kg: float
    w_per_kg: float


class WeightTrend(_Model):
    method: str
    tau_days: float
    points: list[WeightPoint] = []
    latest_trend_kg: Optional[float] = None
    change_28d_kg: Optional[float] = None
    wkg: list[WkgPoint] = []
    latest_w_per_kg: Optional[float] = None


class CpFitPoint(_Model):
    duration_s: int
    watts: int
    work_j: int


class CpFit(_Model):
    status: str                               # ok | insufficient | out_of_range
    reason: str = ""
    n_points: int = 0
    points: list[CpFitPoint] = []
    cp_w: Optional[float] = None
    wprime_j: Optional[int] = None
    cp_se_w: Optional[float] = None
    wprime_se_j: Optional[int] = None
    cp_ci95_w: Optional[list[float]] = None
    wprime_ci95_j: Optional[list[int]] = None
    r2: Optional[float] = None
    see_j: Optional[int] = None


class CpHistoryPoint(_Model):
    end_date: str
    status: str
    cp_w: Optional[float] = None
    wprime_j: Optional[int] = None
    cp_ci95_w: Optional[list[float]] = None
    pmax_w: Optional[int] = None


class PowerModel(_Model):
    window_days: int
    n_rides: int
    method: str
    caveat: str
    fit: CpFit
    pmax_w: Optional[int] = None
    weight_kg: Optional[float] = None
    cp_w_per_kg: Optional[float] = None
    history: list[CpHistoryPoint] = []


class CompareSummary(_Model):
    duration_s: Optional[float] = None
    distance_km: Optional[float] = None
    np_w: Optional[float] = None
    if_pct: Optional[float] = None
    tss: Optional[float] = None
    avg_hr: Optional[float] = None
    avg_power_w: Optional[float] = None


class CompareSide(_Model):
    ride_id: Optional[str] = None
    name: str = "Ride"
    started_at: Optional[str] = None
    whole: bool = True                       # False: an effort (start_s..end_s) of the ride
    start_s: int = 0
    end_s: int = 0
    summary: CompareSummary
    power_w: list[Optional[float]] = []      # one value per bin_s seconds from the side's start
    hr_bpm: list[Optional[float]] = []


class BestEffortDelta(_Model):
    duration_s: int
    a_w: int
    b_w: int
    delta_w: int                             # b - a


class RideCompare(_Model):
    bin_s: int
    min_best_effort_s: int
    a: CompareSide
    b: CompareSide
    delta: CompareSummary                    # b - a per summary field
    best_efforts: list[BestEffortDelta] = []


# ── #121 race predictor (routes_predict.py, race_predictor.py) ───────────────
class RaceInputRun(_Model):
    id: str
    date: Optional[str] = None
    name: str = ""
    distance_m: float
    time_s: float
    pace_s_per_km: float


class RaceInputCs(_Model):
    cs_m_per_s: float
    d_prime_m: float
    date: Optional[str] = None


class RacePrediction(_Model):
    race: str                                # 5k | 10k | half | marathon
    label: str
    distance_m: float
    model: str                               # riegel | critical_speed
    status: str                              # ok | not_enough_long_run | out_of_range | not_supported
    time_s: Optional[float] = None
    pace_s_per_km: Optional[float] = None
    range_text: Optional[str] = None         # only where a published error can be cited
    notes: list[str] = []


class RacePredictor(_Model):
    window_days: int
    best_run: Optional[RaceInputRun] = None
    longest_run_m: Optional[float] = None
    critical_speed: Optional[RaceInputCs] = None
    predictions: list[RacePrediction] = []
    missing: list[str] = []
    riegel_method: str
    riegel_confidence: str
    cs_method: str
    cs_confidence: str
    long_run_rule: str
# ── Nutrition (SparkyFitness) and fueling (#112) ──────────────────────────────

class NutritionConnection(_Model):
    configured: bool = False
    base_url: str = ""
    has_key: bool = False             # the key itself is never returned
    last_synced_at: Optional[str] = None


class NutritionTest(_Model):
    ok: bool
    message: str


class NutritionSync(_Model):
    start: str
    end: str
    days_with_data: int
    synced_at: str


class NutritionDay(_Model):
    date: str
    source: str
    kcal: Optional[float] = None
    carbs_g: Optional[float] = None
    protein_g: Optional[float] = None
    fat_g: Optional[float] = None
    water_ml: Optional[float] = None
    synced_at: Optional[str] = None


class FuelingSession(_Model):
    session_type: str
    duration_min: int


class FuelingDuring(_Model):
    band: str                         # none | small | moderate | high
    low_g_per_h: int
    high_g_per_h: int
    low_g: int
    high_g: int
    note: str


class FuelingDay(_Model):
    load: str                         # light | moderate | high | very_high
    low_g_per_kg: int
    high_g_per_kg: int
    low_g: int
    high_g: int


class Fueling(_Model):
    date: str
    weight_kg: Optional[float] = None
    session: Optional[FuelingSession] = None
    during: Optional[FuelingDuring] = None
    day: Optional[FuelingDay] = None
    logged: Optional[NutritionDay] = None
    connected: bool = False
    ride_kcal_approx: Optional[int] = None
    hourly_method: str
    daily_method: str
    energy_method: str
    note: str
# ── Weather forecast for planned outdoor sessions (#117) ──────────────────────────────────────────────
class WeatherPlace(_Model):
    name: str
    region: str = ""
    country: str = ""
    latitude: float                          # rounded to 2 decimals (~1 km)
    longitude: float


class WeatherLocation(_Model):
    has_location: bool
    place: Optional[WeatherPlace] = None
    network_enabled: bool = True             # False when SHEPHERD_NO_NET=1


class WeatherSearch(_Model):
    available: bool
    message: str = ""
    results: list[WeatherPlace] = []


class WeatherDay(_Model):
    date: str
    rating: str                              # good | marginal | poor (heuristic defaults)
    reasons: list[str] = []
    suggest_indoor: bool = False
    summary: str = ""
    temp_min_c: Optional[int] = None
    temp_max_c: Optional[int] = None
    feels_min_c: Optional[int] = None
    feels_max_c: Optional[int] = None
    rain_pct_max: Optional[int] = None
    rain_mm: float = 0
    gust_max_kmh: Optional[int] = None
    wind_max_kmh: Optional[int] = None


class WeatherAttribution(_Model):
    text: str
    url: str


class WeatherForecast(_Model):
    status: str                              # ok | no_location | unavailable
    days: list[WeatherDay] = []
    attribution: WeatherAttribution
    message: str = ""
# ── #122 swim CSS, sTSS, stroke data; #126 open-water notes (routes_swim.py) ──
class SwimCss(_Model):
    css_s_per_100m: Optional[float] = None
    history: list[SportThresholdEntry] = []
    zones_note: str                          # why swim pace zones are not shown
    method: str
    confidence: str


class SwimCssTest(_Model):
    css_m_per_s: float
    css_s_per_100m: float
    anaerobic_distance_m: float
    r2: Optional[float] = None
    n_trials: int
    method: str
    confidence: str
    saved: bool = False


class SwimActivity(_Model):
    id: str
    date: Optional[str] = None
    name: str = ""
    type: str = ""
    water: str = "unknown"                   # pool | open_water | unknown
    duration_s: float = 0
    distance_m: Optional[float] = None
    pace_s_per_100m: Optional[float] = None
    avg_hr: Optional[float] = None
    icu_load: Optional[float] = None
    intensity: Optional[float] = None
    stss: Optional[float] = None
    pool_length_m: Optional[float] = None
    lengths: Optional[int] = None
    stroke_rate: Optional[float] = None      # intervals.icu average_cadence, as recorded


class SwimActivities(_Model):
    css_s_per_100m: Optional[float] = None
    swims: list[SwimActivity] = []
    missing: list[str] = []
    method: str
    confidence: str
    stroke_note: str


class OpenWaterNote(_Model):
    id: str
    date: str
    activity_id: Optional[str] = None
    water_temp_c: Optional[float] = None
    wetsuit: Optional[bool] = None
    conditions: str = ""
    course: str = ""
    sighting: str = ""
    note: str = ""


class OpenWaterNotes(_Model):
    notes: list[OpenWaterNote] = []
# ── #111 races: A/B/C list, tapers, race-day plan (routes_races.py) ──────────

class RaceTaper(_Model):
    kind: str                            # full (A) | short (B) | opener | easy_day (C) | none
    start: Optional[str] = None
    end: Optional[str] = None
    text: str = ""
    planned_tss: Optional[float] = None  # planned load in the taper window
    before_tss: Optional[float] = None   # B: planned load in the same number of days before it


class Race(_Model):
    id: str
    name: str = ""
    date: str
    priority: str                        # A | B | C
    discipline: str = "cycling"          # cycling | triathlon | running | swimming
    distance: Optional[str] = None       # triathlon only: sprint | olympic | 70.3 | ironman | custom (a label)
    event_type: str = "granfondo"
    event_km: float = 0
    event_climb_m: float = 0
    expected_duration_h: Optional[float] = None
    start_time: Optional[str] = None     # HH:MM
    arrive_time: Optional[str] = None    # HH:MM
    in_plan: bool = False
    days_to_go: int = 0
    taper: RaceTaper


class RaceTaperWeek(_Model):
    start: str
    end: str
    tss_target: float = 0
    planned_tss: float = 0


class RacesStatus(_Model):
    races: list[Race] = []
    stored: bool = False                 # False: read from the plan's goal, nothing saved yet
    has_plan: bool = False
    plan_a_date: Optional[str] = None    # the event plan's goal date (its A race)
    taper_weeks: list[RaceTaperWeek] = []
    plan_synced: bool = False            # the plan's goal changed: rebuild it
    method: str = ""
    confidence: str = ""


class RaceTimelineRow(_Model):
    time: str
    label: str


class RacePower(_Model):
    available: bool
    reason: Optional[str] = None
    ftp: Optional[int] = None
    projected_duration_h: Optional[float] = None
    if_low: Optional[float] = None
    if_high: Optional[float] = None
    np_low: Optional[int] = None
    np_high: Optional[int] = None
    predicted_np: Optional[int] = None
    predicted_if: Optional[float] = None
    predicted_tss: Optional[float] = None
    method: Optional[str] = None
    confidence: Optional[str] = None


class RaceDayPlan(_Model):
    race: Race
    warmup_min: int
    timeline: list[RaceTimelineRow] = []
    expected_duration_h: Optional[float] = None
    power: RacePower
    fueling: str


# ═════════════════════════════════════════════════════════════════════════════
# #10, UI route inventory slice (docs/api-inventory-ui.md). Models for the
# routes the web app calls that had no response model. Every field below was
# seen in a real TestClient response (or its branch, with the network faked).
# Models document; they never validate (see the module docstring).
# ═════════════════════════════════════════════════════════════════════════════
class SetupLimits(_Model):
    """GET /api/setup/limits: [min, max] per setup field."""
    ftp: Optional[list[float]] = None
    weight: Optional[list[float]] = None
    lthr: Optional[list[float]] = None
    max_hr: Optional[list[float]] = None
    hours_per_week: Optional[list[float]] = None
    age: Optional[list[float]] = None
    cp: Optional[list[float]] = None
    wprime_j: Optional[list[float]] = None


class IcuKeyCheck(_Model):
    """POST /api/setup/test-icu: HTTP 200 either way; ``ok`` false carries ``error``."""
    ok: bool
    error: Optional[str] = None
    name: Optional[str] = None
    athlete_id: Optional[str] = None
    eftp: Optional[int] = None
    weight: Optional[float] = None


class ActivitiesCheck(_Model):
    """POST /api/setup/check-activities: HTTP 200 either way; ``ok`` false carries ``error``."""
    ok: bool
    error: Optional[str] = None
    count: Optional[int] = None
    garmin_count: Optional[int] = None
    latest_date: Optional[str] = None


class PickedFolder(_Model):
    """GET /api/setup/pick-folder: "" when the dialog was cancelled or unavailable."""
    path: str = ""


class SetupSaved(_Model):
    """POST /api/setup/save. The optional keys appear only when they apply."""
    ok: bool = True
    creds_test: Optional[str] = None             # "passed" | "failed: <reason>"
    athlete_id_detected: Optional[str] = None
    athlete_name: Optional[str] = None
    warning: Optional[str] = None


class AthleteNumbers(_Model):
    """GET /api/icu/athlete-numbers: null for any value intervals.icu does not hold."""
    ok: bool = False
    ftp: Optional[float] = None
    weight: Optional[float] = None
    lthr: Optional[float] = None
    max_hr: Optional[float] = None


class SyncResult(_Model):
    """POST /api/sync. ``status`` is "skipped" when no credentials are configured."""
    timestamp: str
    wellness: int = 0
    activities: int = 0
    status: str = ""
    error: Optional[str] = None


class DfaBackfillCancelRequested(_Model):
    status: str                                  # "cancel_requested"
    task_id: str


class FrontendErrorLogged(_Model):
    """POST /api/diag/frontend-error: ``code`` is the code that was logged (unknown codes become E_FRONTEND_GENERIC)."""
    ok: bool = True
    code: str
# ── weekly sport balance (#124, actuals half): routes_balance.py ─────────────────────────────────
class BalanceBucket(_Model):
    key: str
    label: str
    start: str
    end: str
    hours: dict[str, float]
    load: dict[str, float]
    total_hours: float
    total_load: float
    hours_share: dict[str, Optional[float]]
    load_share: dict[str, Optional[float]]
    gap_pp: Optional[dict[str, float]] = None    # actual share of hours minus target, percentage points


class BalanceTargets(_Model):
    targets: Optional[dict[str, float]] = None   # percent of weekly hours per sport, summing to 100; None = not set
    has_targets: bool = False
    limiter: Optional[str] = None
    limiter_note: str = ""


class Balance(BalanceTargets):
    as_of: str
    weeks: list[BalanceBucket] = []
    months: list[BalanceBucket] = []
    sports_present: list[str] = []
    single_sport: Optional[str] = None
    has_history: bool = False
    method: str = ""


# ── Gear (#115) ─────────────────────────────────────────────────────────────────────────────────────
class GearService(_Model):
    date: str
    note: str = ""


class GearItem(_Model):
    id: str
    name: str
    kind: str                            # bike | shoes | component
    parent_id: Optional[str] = None      # a component's bike
    retired: bool = False
    started_on: Optional[str] = None
    icu_name: Optional[str] = None       # the intervals.icu gear name that maps rides to this item
    service_every_km: Optional[float] = None
    service_every_hours: Optional[float] = None
    km: float = 0                        # since the counter start (started_on or the last service day)
    hours: float = 0
    km_pct: Optional[float] = None       # km / service_every_km
    hours_pct: Optional[float] = None
    state: str                           # ok | due_soon | due | no_threshold | retired
    last_service: Optional[str] = None
    services: list[GearService] = []


class GearSuggestion(_Model):
    icu_name: str
    rides: int


class GearRide(_Model):
    id: str
    date: str
    name: Optional[str] = None
    sport: Optional[str] = None
    distance_km: Optional[float] = None
    gear_id: Optional[str] = None
    source: str                          # manual | auto | none


class GearOverview(_Model):
    items: list[GearItem] = []
    suggestions: list[GearSuggestion] = []
    recent: list[GearRide] = []
    method: str = ""


# ── Folder import (#31 Phase 1) ──────────────────────────────────────────────
class FolderImportFailure(_Model):
    file: str
    reason: str


class FolderImportScan(_Model):
    started_at: str
    finished_at: str = ""
    imported: int = 0
    duplicate: int = 0                   # already stored (intervals.icu or an earlier import)
    failed: int = 0
    already_imported: int = 0            # files a previous scan handled
    remaining: int = 0                   # new files left for the next scan (per-scan cap)
    aborted: bool = False
    error: str = ""
    failures: list[FolderImportFailure] = []


class FolderImportState(_Model):
    folder: str = ""
    recursive: bool = False
    running: bool = False
    max_files: int
    last_scan: Optional[FolderImportScan] = None


class FolderImportStarted(_Model):
    started: bool                        # False: a scan was already running
    running: bool
# ── Companion sessions in the plan (ADDENDUM 5): routes_multisport_plan.py ───────────────────────────
class PlanCompanion(_Model):
    id: str
    day: str
    day_name: str = ""
    sport: str                           # running | swimming | strength
    session_type: str                    # run_easy | swim_endurance | strength | ...
    duration_min: int = 0
    description: str = ""
    status: str = "pending"              # pending | done | missed | dismissed
    hard: bool = False
    template_id: str = ""
    workout: Optional[dict] = None       # steps in the workout_builder shape
    dismissed_at: str = ""
    completion_matches: Optional[list] = None
    brick_of: Optional[str] = None       # a brick run: the bike session it follows (cycling-<date>)
    brick_note: Optional[str] = None     # the rider's note on how the run felt off the bike
    limiter: Optional[str] = None        # one line: why the limiter sport got this slot


class PlanCompanionWeek(_Model):
    week_num: Optional[int] = None
    start: str
    end: str
    companions: list[PlanCompanion] = []


class PlanCompanions(_Model):
    enabled: bool = False                # the rider's sport targets turn companion planning on
    has_plan: bool = False
    note: str = ""                       # "not validated against real runs/swims yet"
    today: list[PlanCompanion] = []
    transition_target_s: Optional[int] = None   # the rider's brick transition-time target (no default)
    weeks: list[PlanCompanionWeek] = []


class CompanionDismissed(_Model):
    ok: bool = True
    companion: PlanCompanion



# ── Strength and mobility sessions (#127): routes_strength.py ────────────────────────────────────────
class StrengthExercise(_Model):
    id: str
    name: str
    pattern: str
    cue: str
    per_side: bool = False
    sets: list[int]                      # [fewest, most]
    reps: Optional[list[int]] = None     # [fewest, most]; None for a timed hold
    hold_s: Optional[int] = None
    rpe: list[int]                       # CR10 effort per set, [low, high]
    effort: str
    rest: str


class StrengthProgression(_Model):
    sets: list[int]
    reps: list[int]
    rest: str
    pct_1rm: str
    verify: bool = False                 # True: ranges not checked against the paper yet


class StrengthSession(_Model):
    id: str
    name: str
    kind: str                            # strength | maintenance | mobility
    intent: str
    minutes: int
    minutes_range: list[int]
    stage: str
    stage_label: str
    hard: bool = False
    exercises: list[StrengthExercise]
    rpe_range: list[int]                 # design RPE of the whole session
    load_au: list[float]                 # [low, high] minutes x RPE
    load_note: str                       # "arbitrary units (session-RPE), not comparable with TSS"
    load_method: str
    progression: Optional[StrengthProgression] = None
    warmup_min: int = 0
    disclaimer: str
    not_validated: str
    source: str


class StrengthStage(_Model):
    id: str
    label: str
    sets: list[int]
    reps: list[int]
    rpe: list[int]
    effort: str
    rest: str
    pct_1rm: str
    source: str
    verify: bool = False


class StrengthSessions(_Model):
    stage: str
    stages: list[StrengthStage]
    sessions: list[StrengthSession]
    disclaimer: str
    not_validated: str
    load_note: str
    load_method: str
    sources: list[str]
# ── Swim session library (routes_swim_sessions.py) ──────────────────────────────────────────────
class SwimSession(_Model):
    id: str
    name: str
    kind: str                            # easy | recovery | endurance | css | threshold
    session_type: str                    # swim_endurance | swim_css
    intent: str
    hard: bool = False
    minutes: int                         # the length the set text is written for
    minutes_min: int
    minutes_max: int
    lines: list[str] = []                # the set text, one line per part
    note: str = ""                       # pool length, and "no CSS saved" when that is so


class SwimSessions(_Model):
    css_s_per_100m: Optional[float] = None
    has_css: bool = False
    pool_m: int = 25
    source: str = ""                     # Wakayoshi 1992/1993; set shapes are coaching templates
    not_validated: str = ""
    download_note: str = ""              # plain text only, no FIT
    sessions: list[SwimSession] = []
# ── Run session library (#120): routes_run_sessions.py ─────────────────────────────────────────────────
class RunProfilePoint(_Model):
    x: float                             # minutes
    y: float                             # % of threshold speed at the step's intended zone


class RunSession(_Model):
    id: str
    name: str
    kind: str                            # easy | long | recovery | strides | tempo | cruise | intervals | hills
    session_type: str
    stimulus: str                        # recovery | aerobic | threshold | vo2max | speed
    daniels: str                         # Daniels category: E | T | I | R
    intent: str
    hard: bool
    min_minutes: int
    max_minutes: int
    minutes: int                         # the length the workout below is built for
    workout: dict                        # workout_builder shape; pace_pct_threshold or effort targets
    rtss_estimate: float                 # run_metrics.rtss at the intended zones: an estimate
    profile: list[RunProfilePoint] = []
    source: str = ""


class RunSessions(_Model):
    threshold_pace_s_per_km: Optional[float] = None
    targets: str                         # "pace" (threshold pace saved) | "effort"
    note: str                            # design templates after Daniels; not validated against recorded runs
    method: str
    sessions: list[RunSession] = []


# ── Multi-sport engine wave 2 (ENGINE): bricks (#123) ─────────────────────────

class BrickTransition(_Model):
    ok: bool = True
    transition_target_s: Optional[int] = None
