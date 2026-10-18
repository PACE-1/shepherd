"""#113: the injury/illness hook in training_planner must leave every existing plan as it was.

Runs the planner characterization (tests/characterize_planner.py: every entry point, generate,
regenerate, extend, recalculate, refit, reforecast, over continuous, event, blueprint and CTL riders)
against its checked-in golden, tests/characterization.json. None of those fixtures has an injury or
illness episode, so all of them must come out unchanged. test_injury.py covers the time-off rows the
Plan form writes (holiday, injury, illness without an episode) on the regenerate path.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def test_existing_fixtures_produce_byte_identical_plans():
    out = subprocess.run([sys.executable, str(HERE / "characterize_planner.py")], capture_output=True, check=False,
                         text=True, timeout=600, cwd=str(HERE.parent))
    assert out.returncode == 0, (out.stdout + out.stderr)[-3000:]
    assert "all unchanged" in out.stdout and " changed (" not in out.stdout
