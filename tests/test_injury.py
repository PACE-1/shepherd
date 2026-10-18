"""#113 injury and illness: episodes, plan time off, the return ramp in the planner, the ramp-rate warning."""
import json
from datetime import date, timedelta
from itertools import pairwise

import pytest

import clock
import injury
import training_planner as tp

TODAY = date(2026, 9, 14)  # a Monday


# ── episodes ────────────────────────────────────────────────────────────────────────────────────────
def test_episodes_are_stored_open_until_resolved_and_can_be_deleted(tmp_path):
    p = tmp_path / injury.FILE_NAME
    ep = injury.add_episode(p, type="illness", start="2026-09-10", note="cold", body_area="")
    assert ep["end"] is None and injury.read_episodes(p)[0]["note"] == "cold"
    injury.resolve_episode(p, ep["id"], "2026-09-12")
    assert injury.read_episodes(p)[0]["end"] == "2026-09-12"
    injury.delete_episode(p, ep["id"])
    assert injury.read_episodes(p) == []


@pytest.mark.parametrize("kw, msg", [
    ({"type": "flu", "start": "2026-09-10"}, "injury or illness"),
    ({"type": "injury", "start": "10/09/2026"}, "date"),
    ({"type": "injury", "start": "2026-09-10", "end": "2026-09-01"}, "before start"),
    ({"type": "injury", "start": "2026-09-10", "sport": "chess"}, "sport"),
])
def test_bad_episodes_are_refused(tmp_path, kw, msg):
    with pytest.raises(ValueError, match=msg):
        injury.add_episode(tmp_path / "e.json", **kw)


def test_unknown_ids_and_bad_resolve_dates(tmp_path):
    p = tmp_path / "e.json"
    ep = injury.add_episode(p, type="injury", start="2026-09-10")
    with pytest.raises(KeyError):
        injury.resolve_episode(p, "nope", "2026-09-12")
    with pytest.raises(KeyError):
        injury.delete_episode(p, "nope")
    with pytest.raises(ValueError):
        injury.resolve_episode(p, ep["id"], "2026-09-01")
    assert injury.read_episodes(p)[0]["end"] is None


def test_a_corrupt_file_reads_as_empty_and_is_never_overwritten(tmp_path):
    p = tmp_path / "e.json"
    p.write_text("{not json")
    assert injury.read_episodes(p) == []
    with pytest.raises(OSError):
        injury.add_episode(p, type="injury", start="2026-09-10")
    assert p.read_text() == "{not json"


def test_back_today_ends_yesterday_or_on_the_first_day():
    assert injury.back_today_end({"start": "2026-09-01"}, TODAY) == date(2026, 9, 13)
    assert injury.back_today_end({"start": "2026-09-14"}, TODAY) == TODAY


# ── plan time off ──────────────────────────────────────────────────────────────────────────────────
def _plan():
    return {"weeks": [{"start": "2026-09-14", "end": "2026-09-20"}, {"start": "2026-09-21", "end": "2026-09-27"}],
            "unavailable_periods": [{"start": "2026-10-01", "end": "2026-10-03", "type": "holiday", "daily_tss": 25, "reason": ""}]}


def test_sync_keeps_other_time_off_pauses_to_plan_end_and_skips_other_sports():
    plan = _plan()
    eps = [{"id": "a", "type": "illness", "start": "2026-09-12", "end": None, "sport": "all"},
           {"id": "b", "type": "injury", "start": "2026-09-01", "end": "2026-09-05", "sport": "running"}]
    assert injury.sync_plan_periods(plan, eps, TODAY) is True
    rows = plan["unavailable_periods"]
    assert rows[0]["type"] == "holiday"
    assert rows[1] == {"start": "2026-09-12", "end": "2027-09-14", "type": "illness", "daily_tss": 0,
                       "reason": "illness", "episode_id": "a", "open": True}
    assert len(rows) == 2  # the running-only injury does not pause the cycling plan
    assert injury.sync_plan_periods(plan, eps, TODAY) is False  # unchanged on a second run
    eps[0]["end"] = "2026-09-13"
    injury.sync_plan_periods(plan, eps, TODAY)
    assert plan["unavailable_periods"][1]["end"] == "2026-09-13" and not plan["unavailable_periods"][1]["open"]
    injury.sync_plan_periods(plan, [], TODAY)
    assert plan["unavailable_periods"] == _plan()["unavailable_periods"]


def _row(start, end, **kw):
    return {"start": start, "end": end, "type": "injury", "episode_id": "x", **kw}


def test_return_ramp_only_for_finished_episode_rows():
    legacy = {"start": "2026-09-01", "end": "2026-09-10", "type": "injury"}
    assert injury.return_ramp([legacy], TODAY) is None          # no episode_id: never a ramp
    assert injury.return_ramp(None, TODAY) is None
    assert injury.return_ramp([_row("2026-09-10", "2026-09-30", open=True)], TODAY) is None
    assert injury.return_ramp([_row("2026-09-10", "2026-09-14")], TODAY) is None   # still covers today
    assert injury.return_ramp([_row("2026-09-20", "2026-09-22")], TODAY) is None   # in the future
    r = injury.return_ramp([_row("2026-09-11", "2026-09-13")], TODAY)       # an injury, however short, gets the ramp
    assert (r["episode_days"], r["absence_days"], r["weeks_done"]) == (3, 7, 0)
    r = injury.return_ramp([_row("2026-08-01", "2026-08-21"), _row("2026-08-25", "2026-09-05")], TODAY)
    assert (r["start"], r["episode_days"], r["absence_days"], r["weeks_done"]) == ("2026-08-25", 12, 12, 1)


def test_episode_days_ignores_other_rows():
    days = injury.episode_days([_row("2026-09-01", "2026-09-03"), {"start": "2026-09-05", "end": "2026-09-06"}])
    assert days == {date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3)}


# ── ramp-rate warning: thresholds of Gabbett 2016 (1.3 sweet-spot ceiling, 1.5 danger zone) ─────────
def _acts(this_week, prev_week, sport="Ride"):
    rows = [{"date": (TODAY - timedelta(days=d)).isoformat(), "sport": sport, "tss": this_week} for d in (0,)]
    for k in range(1, 5):
        rows.append({"date": (TODAY - timedelta(days=7 * k + 1)).isoformat(), "sport": sport, "tss": prev_week})
    return rows


@pytest.mark.parametrize("load, level, warn", [(130, "ok", False), (131, "elevated", True), (149, "elevated", True),
                                               (150, "high", True), (60, "ok", False)])
def test_ramp_rate_levels_at_the_published_thresholds(load, level, warn):
    r = injury.ramp_rate(_acts(load, 100), TODAY)
    assert r["combined"]["prev_4wk_avg"] == 100 and r["combined"]["level"] == level
    assert r["sports"]["cycling"]["level"] == level and r["warn"] is warn
    assert r["combined"]["ratio"] == pytest.approx(load / 100)


def test_ramp_rate_per_sport_and_without_a_base():
    acts = _acts(100, 100) + [{"date": TODAY.isoformat(), "sport": "Run", "tss": 40}]
    r = injury.ramp_rate(acts, TODAY)
    assert r["sports"]["running"]["level"] == "no_base" and r["sports"]["running"]["ratio"] is None
    assert r["sports"]["cycling"]["level"] == "ok"
    assert r["combined"]["ratio"] == 1.4 and r["warn"] and r["warnings"][0].startswith("All sports: ")
    assert "Not medical advice" in r["note"] and r["confidence"]


# ── the planner's return ramp (training_planner.regenerate_from_today) ──────────────────────────────
ATHLETE = {"ftp": 240, "weight_kg": 72}
HARD = {"vo2max", "threshold", "sweetspot", "overunder", "tempo", "sprint", "anaerobic"}


@pytest.fixture
def frozen(monkeypatch):
    cur = [TODAY]

    class _D(date):
        @classmethod
        def today(cls):
            return cls(cur[0].year, cur[0].month, cur[0].day)

    monkeypatch.setattr(tp, "date", _D)

    def at(d):
        cur[0] = d
        clock.freeze(d)
    at(TODAY)
    yield at
    clock.unfreeze()


def _goal():
    avail = [1, 2, 3, 4, 5, 6]
    return tp.Goal(goal_type="continuous", rest_days=[0], available_days=avail, daily_max_hours={d: 1.5 for d in avail})


def _regen(at, periods, days_on, ridden=True):
    """Rebuild ``days_on`` days into a fresh plan. ``ridden``: every past session was ridden as planned, so
    the planner's own absence detection stays quiet and only the episode can bring a ramp."""
    at(TODAY)
    base = tp.generate_plan(_goal(), seed_salt=7, current_ctl=45.0, recent_weekly_tss=320.0, athlete=ATHLETE)[1]
    today = TODAY + timedelta(days=days_on)
    rides = [{"date": s.day.isoformat(), "sport": "Ride", "tss": s.tss_estimate}
             for w in base for s in w.sessions if s.day < today and s.tss_estimate] if ridden else None
    at(today)
    _ph, weeks, info = tp.regenerate_from_today(_goal(), base, 45.0, unavailable_periods=periods, activities=rides,
                                                seed_salt=7, athlete=ATHLETE, recent_weekly_tss=320.0)
    return today, weeks, info


def test_a_finished_episode_puts_an_easy_only_ramp_after_it(frozen):
    start = TODAY + timedelta(days=7)
    rows = [_row(start.isoformat(), (start + timedelta(days=9)).isoformat())]   # 10 days ill
    today, weeks, info = _regen(frozen, rows, 17)                               # back today
    assert info["injury_return"]["absence_days"] == 10 and info["injury_return"]["weeks_done"] == 0
    ramp = [w for w in weeks if w.phase in ("recon", "recovery_ramp")]
    assert [w.phase for w in ramp] == ["recon", "recovery_ramp", "recovery_ramp"]   # the <= 2-week tier
    assert ramp[0].start == today
    assert all(s.session_type in ("z2", "rest") for w in ramp for s in w.sessions)
    targets = [w.tss_target for w in ramp]
    assert all(b > a and b / a <= 1.3 for a, b in pairwise(targets))


def test_a_rebuild_a_week_later_continues_the_ramp(frozen):
    start = TODAY + timedelta(days=3)
    rows = [_row(start.isoformat(), (start + timedelta(days=4)).isoformat())]  # ends day 7, back day 8
    _t, weeks, info = _regen(frozen, rows, 15)
    assert info["injury_return"]["weeks_done"] == 1
    assert [w.phase for w in weeks if w.phase in ("recon", "recovery_ramp")] == ["recovery_ramp", "recovery_ramp"]


def test_an_open_episode_rests_the_rest_of_the_plan(frozen):
    plan = {"weeks": []}   # the row exactly as the routes write it on day 10
    injury.sync_plan_periods(plan, [{"id": "x", "type": "illness", "start": (TODAY + timedelta(days=8)).isoformat(),
                                     "end": None}], TODAY + timedelta(days=10))
    # Nothing ridden in week 1, so the planner's own absence ramp runs (and lengthens the plan): all must rest.
    today, weeks, info = _regen(frozen, plan["unavailable_periods"], 10, ridden=False)
    assert "injury_return" not in info and info["recovery_ramp_weeks"] > 0
    future = [s for w in weeks for s in w.sessions if s.day >= today]
    assert future and all(s.session_type == "rest" for s in future)


def _dump(weeks, info):
    return json.dumps([tp.week_to_dict(w) for w in weeks], sort_keys=True, default=str) + json.dumps(
        info, sort_keys=True, default=str)


def test_plans_without_episode_rows_are_byte_identical_with_the_hook_switched_off(frozen, monkeypatch):
    """The existing time-off rows (holiday, and the Plan form's own injury/illness rows) carry no
    episode_id, so the #113 hook must not move a byte of the plan."""
    rows = [{"start": (TODAY + timedelta(days=12)).isoformat(), "end": (TODAY + timedelta(days=14)).isoformat(),
             "type": "holiday", "daily_tss": 25, "reason": ""},
            {"start": (TODAY + timedelta(days=2)).isoformat(), "end": (TODAY + timedelta(days=6)).isoformat(),
             "type": "injury", "daily_tss": 0, "reason": ""}]
    for periods in (None, rows):
        on = _dump(*_regen(frozen, periods, 10, ridden=False)[1:])  # week 1 missed: the absence ramp runs too
        with monkeypatch.context() as m:
            m.setattr(injury, "return_ramp", lambda *_a, **_k: None)
            m.setattr(injury, "episode_days", lambda *_a, **_k: set())
            off = _dump(*_regen(frozen, periods, 10, ridden=False)[1:])
        assert on == off


# ── endpoints ───────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import app
    import routes_injury
    monkeypatch.setattr(routes_injury, "_plan_dir", lambda: tmp_path)
    monkeypatch.setattr(routes_injury, "_episodes_path", lambda: tmp_path / injury.FILE_NAME)
    clock.freeze(TODAY)
    yield TestClient(app.app), tmp_path
    clock.unfreeze()


def test_endpoints_record_resolve_and_delete_and_mirror_into_the_plan(client):
    c, d = client
    (d / "current_plan.json").write_text(json.dumps(_plan()))
    assert c.get("/api/injury").json()["episodes"] == []
    assert c.post("/api/injury/episodes", json={"type": "cold", "start": "2026-09-12"}).status_code == 400
    r = c.post("/api/injury/episodes", json={"type": "illness", "start": "2026-09-12", "note": "flu"}).json()
    assert r["plan_synced"] and r["active"]["note"] == "flu" and r["has_plan"] and "Not medical advice" in r["note"]
    eid = r["episodes"][0]["id"]
    plan = json.loads((d / "current_plan.json").read_text())
    assert plan["unavailable_periods"][-1]["episode_id"] == eid and plan["unavailable_periods"][-1]["end"] == "2027-09-14"
    r = c.post(f"/api/injury/episodes/{eid}/resolve", json={}).json()       # "I'm back"
    assert r["episodes"][0]["end"] == "2026-09-13" and r["active"] is None
    assert r["return_ramp"] is None and r["plan_synced"]   # a 2-day flu: no forced ramp (SCIENCE.md 1b governs)
    assert c.post("/api/injury/episodes/nope/resolve", json={}).status_code == 404
    assert c.delete(f"/api/injury/episodes/{eid}").json()["episodes"] == []
    assert json.loads((d / "current_plan.json").read_text())["unavailable_periods"] == _plan()["unavailable_periods"]
    assert c.delete(f"/api/injury/episodes/{eid}").status_code == 404


def test_episodes_without_a_plan_are_stored_and_ramp_rate_answers(client):
    c, _d = client
    r = c.post("/api/injury/episodes", json={"type": "injury", "start": "2026-09-01", "end": "2026-09-03",
                                            "sport": "running", "body_area": "knee"}).json()
    assert not r["has_plan"] and not r["plan_synced"] and r["episodes"][0]["body_area"] == "knee"
    rr = c.get("/api/injury/ramp-rate")
    assert rr.status_code == 200 and set(rr.json()["combined"]) >= {"week_load", "prev_4wk_avg", "ratio", "level"}


def test_a_short_illness_gets_no_forced_ramp_but_a_long_one_does():
    short = _row("2026-08-31", "2026-09-13", type="illness")                 # 14 days
    assert injury.return_ramp([short], TODAY) is None                         # the planner's 1b re-entry rule applies
    assert injury.return_ramp([_row("2026-09-11", "2026-09-13", type="illness")], TODAY) is None
    r = injury.return_ramp([_row("2026-08-30", "2026-09-13", type="illness")], TODAY)   # 15 days
    assert r["episode_days"] == 15 and r["absence_days"] == 15
