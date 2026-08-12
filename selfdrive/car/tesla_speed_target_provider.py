from dataclasses import dataclass

from opendbc.car.common.conversions import Conversions as CV
from openpilot.common.params import Params


TESLA_TARGET_MAX_AGE_NS = 1_500_000_000
TESLA_CONFIRM_FRAMES = 2
MIN_TARGET_KPH = 30.0
MAX_TARGET_KPH = 200.0


@dataclass(frozen=True)
class TeslaSpeedTarget:
  speed_mps: float
  speed_kph: float
  fused_limit_kph: float
  offset_kph: int
  valid: bool
  source: str
  timestamp_nanos: int


class TeslaSpeedTargetProvider:
  """Build a stable Tesla set-speed target only from its fused map limit."""

  def __init__(self, params: Params | None = None):
    self.params = params or Params()
    self.offset_kph = self.params.get_int("AutoRoadSpeedLimitOffset")
    self._candidate_kph: float | None = None
    self._candidate_frames = 0
    self._last_nanos = 0

  def latch_offset(self) -> None:
    self.offset_kph = self.params.get_int("AutoRoadSpeedLimitOffset")

  def update(self, fused_limit_kph: float, fused_limit_valid: bool, fused_limit_nanos: int,
             now_nanos: int) -> TeslaSpeedTarget:
    fused_limit_nanos = int(fused_limit_nanos)
    now_nanos = int(now_nanos)
    fresh = (fused_limit_valid and fused_limit_nanos > 0 and now_nanos >= fused_limit_nanos and
             now_nanos - fused_limit_nanos <= TESLA_TARGET_MAX_AGE_NS)
    if not fresh or self.offset_kph < 0:
      self._candidate_kph = None
      self._candidate_frames = 0
      self._last_nanos = 0
      source = "disabled" if self.offset_kph < 0 else "stale" if fused_limit_valid else "invalid"
      return TeslaSpeedTarget(0.0, 0.0, float(fused_limit_kph), self.offset_kph, False, source, fused_limit_nanos)

    fused_limit_kph = float(fused_limit_kph)
    if fused_limit_nanos != self._last_nanos:
      if self._candidate_kph == fused_limit_kph:
        self._candidate_frames += 1
      else:
        self._candidate_kph = fused_limit_kph
        self._candidate_frames = 1
      self._last_nanos = fused_limit_nanos

    target_kph = fused_limit_kph + self.offset_kph
    confirmed = self._candidate_frames >= TESLA_CONFIRM_FRAMES
    valid = confirmed and MIN_TARGET_KPH <= target_kph <= MAX_TARGET_KPH
    source = "tesla_fused" if valid else "confirming" if not confirmed else "out_of_range"
    return TeslaSpeedTarget(target_kph * CV.KPH_TO_MS if valid else 0.0,
                            target_kph if valid else 0.0, fused_limit_kph, self.offset_kph,
                            valid, source, fused_limit_nanos)
