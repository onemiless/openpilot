from pathlib import Path

from openpilot.sunnypilot.modeld_v2.egpu_loader import C3XL_MODEL_LOAD_TIMEOUT


def test_c3xl_model_load_timeout_covers_measured_loads():
  assert C3XL_MODEL_LOAD_TIMEOUT == 120
  assert C3XL_MODEL_LOAD_TIMEOUT >= 75.58 * 1.5


def test_both_model_runners_use_shared_timeout():
  root = Path(__file__).parents[4]
  for relative_path in ("openpilot/selfdrive/modeld/modeld.py", "openpilot/sunnypilot/modeld_v2/modeld.py"):
    source = (root / relative_path).read_text()
    assert "BIG_MODEL_TIMEOUT = C3XL_MODEL_LOAD_TIMEOUT" in source
