"""compute_ride_xss must call the real strain_score function (it passed `wprime_j=` to a `w_prime` parameter, so it never computed anything)."""
import ride_storage


def test_a_power_trace_gets_a_strain_score_on_the_summary():
    summary = {}
    out = ride_storage.compute_ride_xss([220.0] * 600 + [350.0] * 300, started_at=None, summary=summary, cp=250, wprime_j=20000, pmax=1000)
    assert out and summary["xss_total"] is not None and summary["xss_total"] > 0
