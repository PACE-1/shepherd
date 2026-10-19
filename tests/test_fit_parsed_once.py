"""#163 — the readers of one ride share a single parse of its FIT."""
import os
from unittest.mock import patch

import app as app_module
import fit_activity
from fit_tool.fit_file import FitFile
from test_hrtss_ingestion import _build_fit


def test_all_readers_parse_the_file_once(tmp_path):
    fit = _build_fit(tmp_path / "a.fit", n=6, power=[0, 150, 300, 250, 180, 90], hr=120)
    fit_activity._FIT_CACHE.clear()
    with patch.object(FitFile, "from_file", wraps=FitFile.from_file) as spy:
        app_module._parse_fit_stats(fit)
        fit_activity.parse_device_info(fit)
        fit_activity.parse_rr_intervals(fit)
        fit_activity.read_session_sport(fit)
        fit_activity.parse_record_streams(fit)
        app_module._build_fit_samples(fit)
    assert spy.call_count == 1


def test_rewritten_file_is_parsed_again(tmp_path):
    fit = _build_fit(tmp_path / "b.fit", n=4, hr=120)
    fit_activity._FIT_CACHE.clear()
    fit_activity.load_fit(fit)
    os.utime(fit, ns=(1, 2))
    with patch.object(FitFile, "from_file", wraps=FitFile.from_file) as spy:
        fit_activity.load_fit(fit)
    assert spy.call_count == 1
