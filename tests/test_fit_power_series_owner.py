"""#23 — the backfill's power reader and parse_record_streams are one walk."""
import app as app_module
import fit_activity
from test_hrtss_ingestion import _build_fit


def test_backfill_power_series_matches_parse_record_streams(tmp_path):
    fit = _build_fit(tmp_path / "a.fit", n=6, power=[0, 150, 300, 250, 180, 90], hr=120)
    assert app_module._v136_extract_fit_power_series(fit) == [0, 150, 300, 250, 180, 90]
    assert app_module._v136_extract_fit_power_series(fit) == fit_activity.parse_record_streams(fit)["power"]


def test_file_without_power_reads_as_zeros(tmp_path):
    fit = _build_fit(tmp_path / "b.fit", n=4, hr=130)
    assert app_module._v136_extract_fit_power_series(fit) == [0, 0, 0, 0]


def test_unparseable_file_gives_empty_list(tmp_path):
    bad = tmp_path / "c.fit"
    bad.write_bytes(b"not a fit file")
    assert app_module._v136_extract_fit_power_series(bad) == []
