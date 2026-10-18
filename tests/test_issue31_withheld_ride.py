"""#31 Phase 0: a ride intervals.icu lists but withholds is still a ride.

If intervals.icu stops passing Garmin data on, an activity can still be listed
with its date, sport and length while everything computed from the recording
(load, intensity, power, heart rate) is missing. Before this, the plan matcher
saw a full-length ride with no load and no intensity and could only call the
session partly done; ridden today, it stayed pending. The activity is the
evidence the session was ridden, so a withheld ride that covers the planned
length marks the session done.

Not changed: a Strava-style stub (no sport, no length) still says nothing about
what was ridden, and a short withheld ride does not complete a long session.
"""
from __future__ import annotations

import json

from test_rematch_reads_stored_activity_shapes import MON, MONDAY, TODAY, _reconcile


def _withheld(minutes, day=MONDAY, rid="i31", hour=8):
    """An activities row for a ride intervals.icu listed without its data."""
    return {"id": rid, "date": day.isoformat(), "name": None, "sport": "Ride",
            "duration_sec": minutes * 60, "tss": None, "avg_power": None, "avg_hr": None,
            "raw_json": json.dumps({"id": rid, "source": "GARMIN_CONNECT", "type": "Ride",
                                    "start_date_local": f"{day}T{hour:02d}:00:00",
                                    "elapsed_time": minutes * 60})}


def test_a_withheld_full_length_ride_marks_the_session_done():
    by_day, moves = _reconcile([_withheld(80)])            # planned: 79 min
    assert by_day[MON]["status"] == "done"
    assert by_day[MON]["completion_matches"][0]["activity_id"] == "i31"
    assert moves == []


def test_a_withheld_ride_today_marks_today_done_not_pending():
    by_day, _ = _reconcile([_withheld(75, day=TODAY, rid="i32")])   # planned: 73 min
    assert by_day[TODAY.isoformat()]["status"] == "done"


def test_a_short_withheld_ride_does_not_complete_a_long_session():
    by_day, _ = _reconcile([_withheld(30)])
    assert by_day[MON]["status"] != "done"


def test_a_ride_with_heart_rate_but_no_load_is_judged_as_before():
    """Not withheld: intervals.icu shared the recording, it just had no FTP or
    LTHR to compute a load from. The existing rule (partly done) stands."""
    row = _withheld(80, rid="i33")
    row["avg_hr"] = 140.0
    by_day, _ = _reconcile([row])
    assert by_day[MON]["status"] == "done_partial"


def test_a_stub_with_no_sport_or_length_is_still_not_a_ride():
    stub = {"id": "s1", "date": MON, "sport": "", "duration_sec": None, "tss": None,
            "raw_json": json.dumps({"id": "s1", "source": "GARMIN_CONNECT",
                                    "start_date_local": f"{MONDAY}T08:00:00"})}
    by_day, _ = _reconcile([stub])
    assert by_day[MON]["status"] != "done"
