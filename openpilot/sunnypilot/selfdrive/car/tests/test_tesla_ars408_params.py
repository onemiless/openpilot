from collections import Counter
from pathlib import Path
from typing import Any

from openpilot.sunnypilot.selfdrive.car.interfaces import initialize_params


class CountingParams:
  def __init__(self) -> None:
    self.reads: Counter[str] = Counter()

  def get(self, key: str, *, return_default: bool = False) -> Any:
    self.reads[key] += 1
    assert return_default
    return True if key == "TeslaARS408Radar" else 0


def test_tesla_ars408_radar_is_typed_boolean_with_disabled_default() -> None:
  header = Path("openpilot/common/params_keys.h").read_text()
  assert '{"TeslaARS408Radar", {PERSISTENT | BACKUP, BOOL, "0"}}' in header


def test_tesla_ars408_radar_is_read_once_in_initialization_batch() -> None:
  params = CountingParams()
  cached = initialize_params(params)
  assert params.reads["TeslaARS408Radar"] == 1
  assert {key: value for item in cached for key, value in item.items()}["TeslaARS408Radar"] is True
