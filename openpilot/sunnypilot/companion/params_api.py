from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from openpilot.common.params import Params


READABLE_PARAMS = frozenset(("ExperimentalMode", "ShareData", "SpeedFromPCM"))
WRITABLE_BOOL_PARAMS = READABLE_PARAMS


def _bool_value(value: object) -> bool:
  if isinstance(value, bool):
    return value
  if isinstance(value, int) and value in (0, 1):
    return bool(value)
  if isinstance(value, str) and value.strip().lower() in ("0", "1", "false", "true"):
    return value.strip().lower() in ("1", "true")
  raise ValueError("boolean parameter value must be 0, 1, true, or false")


@dataclass
class ParamAccess:
  params: Params
  is_offroad: Callable[[], bool]

  def read(self, names: list[str]) -> dict[str, int]:
    if not names or len(names) > 16:
      raise ValueError("one to sixteen parameter names are required")
    unknown = sorted(set(names) - READABLE_PARAMS)
    if unknown:
      raise PermissionError(f"parameter is not readable: {unknown[0]}")
    return {name: int(self.params.get_bool(name)) for name in dict.fromkeys(names)}

  def write(self, name: object, value: object) -> None:
    if not isinstance(name, str) or name not in WRITABLE_BOOL_PARAMS:
      raise PermissionError("parameter is not writable")
    if not self.is_offroad():
      raise PermissionError("parameter writes are blocked while onroad")
    self.params.put_bool(name, _bool_value(value))


def params_report_offroad(params: Params) -> bool:
  return params.get_bool("IsOffroad") and not params.get_bool("IsEngaged")
