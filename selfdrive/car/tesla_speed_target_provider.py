from dataclasses import dataclass

from opendbc.car.common.conversions import Conversions as CV
from openpilot.common.params import Params


TARGET_MAX_AGE_NS = 1_000_000_000
MAX_ROAD_LIMIT_KPH = 200.0


@dataclass(frozen=True)
class TeslaSpeedTarget:
  speed_mps: float
  speed_kph: float
  source: str
  valid: bool
  timestamp_nanos: int


class TeslaSpeedTargetProvider:
  """Produces a stable road-limit target without using Carrot composite desiredSpeed."""

  def __init__(self, params: Params | None = None):
    self.params = params or Params()
    self.offset_kph = self.params.get_int("AutoRoadSpeedLimitOffset")

  def refresh_params(self) -> None:
    self.offset_kph = self.params.get_int("AutoRoadSpeedLimitOffset")

  def update(self, carrot_man, _car_state, message_nanos: int, message_valid: bool,
             now_nanos: int) -> TeslaSpeedTarget:
    offset_kph = self.offset_kph
    if offset_kph < 0 or not message_valid or message_nanos <= 0:
      return TeslaSpeedTarget(0.0, 0.0, "none", False, int(message_nanos))
    if int(now_nanos) - int(message_nanos) > TARGET_MAX_AGE_NS:
      return TeslaSpeedTarget(0.0, 0.0, "stale", False, int(message_nanos))

    carrot_active = int(getattr(carrot_man, "activeCarrot", 0)) > 0
    carrot_limit = float(getattr(carrot_man, "nRoadLimitSpeed", 0.0))
    if not carrot_active or carrot_limit <= 0.0:
      return TeslaSpeedTarget(0.0, 0.0, "none", False, int(message_nanos))

    target_kph = carrot_limit + offset_kph
    valid = 0.0 < target_kph <= MAX_ROAD_LIMIT_KPH
    return TeslaSpeedTarget(target_kph * CV.KPH_TO_MS if valid else 0.0,
                            target_kph if valid else 0.0, "carrot" if valid else "invalid",
                            valid, int(message_nanos))
