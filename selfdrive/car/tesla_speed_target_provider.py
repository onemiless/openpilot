from dataclasses import dataclass

from opendbc.car.common.conversions import Conversions as CV
from openpilot.common.params import Params


TARGET_MAX_AGE_NS = 1_000_000_000
TESLA_TARGET_MAX_AGE_NS = 1_500_000_000
MIN_ROAD_LIMIT_KPH = 30.0
MAX_ROAD_LIMIT_KPH = 200.0
TESLA_CONFIRM_FRAMES = 2


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
    self._tesla_candidate_kph: float | None = None
    self._tesla_candidate_frames = 0
    self._tesla_last_nanos = 0

  def refresh_params(self) -> None:
    self.offset_kph = self.params.get_int("AutoRoadSpeedLimitOffset")

  def _confirmed_tesla_limit(self, limit_kph: float, valid: bool, limit_nanos: int,
                             now_nanos: int) -> float | None:
    fresh = (valid and limit_nanos > 0 and now_nanos >= limit_nanos and
             now_nanos - limit_nanos <= TESLA_TARGET_MAX_AGE_NS)
    if not fresh:
      self._tesla_candidate_kph = None
      self._tesla_candidate_frames = 0
      self._tesla_last_nanos = 0
      return None

    if limit_nanos != self._tesla_last_nanos:
      if self._tesla_candidate_kph == limit_kph:
        self._tesla_candidate_frames += 1
      else:
        self._tesla_candidate_kph = limit_kph
        self._tesla_candidate_frames = 1
      self._tesla_last_nanos = limit_nanos

    return self._tesla_candidate_kph if self._tesla_candidate_frames >= TESLA_CONFIRM_FRAMES else None

  @staticmethod
  def _target(limit_kph: float, offset_kph: int, source: str, timestamp_nanos: int) -> TeslaSpeedTarget:
    target_kph = limit_kph + offset_kph
    valid = MIN_ROAD_LIMIT_KPH <= target_kph <= MAX_ROAD_LIMIT_KPH
    return TeslaSpeedTarget(target_kph * CV.KPH_TO_MS if valid else 0.0,
                            target_kph if valid else 0.0, source if valid else "invalid",
                            valid, int(timestamp_nanos))

  def update(self, carrot_man, _car_state, message_nanos: int, message_valid: bool, now_nanos: int, *,
             vehicle_limit_kph: float = 0.0, vehicle_limit_valid: bool = False,
             vehicle_limit_nanos: int = 0) -> TeslaSpeedTarget:
    offset_kph = self.offset_kph
    now_nanos = int(now_nanos)
    tesla_limit = self._confirmed_tesla_limit(float(vehicle_limit_kph), bool(vehicle_limit_valid),
                                               int(vehicle_limit_nanos), now_nanos)
    if offset_kph < 0:
      return TeslaSpeedTarget(0.0, 0.0, "disabled", False, 0)

    carrot_fresh = (message_valid and message_nanos > 0 and now_nanos >= int(message_nanos) and
                    now_nanos - int(message_nanos) <= TARGET_MAX_AGE_NS)
    carrot_active = carrot_fresh and int(getattr(carrot_man, "activeCarrot", 0)) > 0
    carrot_limit = float(getattr(carrot_man, "nRoadLimitSpeed", 0.0))
    if carrot_active and MIN_ROAD_LIMIT_KPH <= carrot_limit <= MAX_ROAD_LIMIT_KPH:
      return self._target(carrot_limit, offset_kph, "carrot", int(message_nanos))

    if tesla_limit is not None:
      return self._target(tesla_limit, offset_kph, "tesla_fused", int(vehicle_limit_nanos))

    source = "stale" if ((message_valid and message_nanos > 0 and not carrot_fresh) or
                         (vehicle_limit_valid and vehicle_limit_nanos > 0 and
                          now_nanos - int(vehicle_limit_nanos) > TESLA_TARGET_MAX_AGE_NS)) else "none"
    return TeslaSpeedTarget(0.0, 0.0, source, False, max(int(message_nanos), int(vehicle_limit_nanos)))
