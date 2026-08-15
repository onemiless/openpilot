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
    return 1 if key == "TeslaRadarBackend" else 0


def test_tesla_radar_backend_is_typed_integer_with_oem_default() -> None:
  header = Path("openpilot/common/params_keys.h").read_text()
  assert '{"TeslaRadarBackend", {PERSISTENT | BACKUP, INT, "0"}}' in header


def test_tesla_radar_backend_is_read_once_in_initialization_batch() -> None:
  params = CountingParams()
  cached = initialize_params(params)
  assert params.reads["TeslaRadarBackend"] == 1
  assert {key: value for item in cached for key, value in item.items()}["TeslaRadarBackend"] == 1
