from __future__ import annotations

from dataclasses import dataclass

from openpilot.common.constants import CV
from openpilot.common.params import Params


PUBLISH_HZ = 10.0
ROUTE_CALC_HZ = 2.0
ROUTE_LOOKAHEAD_M = 300.0
ROUTE_RESAMPLE_M = 5.0
ROUTE_MAX_DEVIATION_M = 40.0
ROUTE_MAX_POINTS = 256
ROUTE_MAX_LAT_ACCEL = 2.0
ROUTE_COMFORT_DECEL = 1.4


@dataclass(frozen=True)
class NavAssistParams:
  enabled: bool
  shadow_mode: bool
  speed_control: bool
  turn_control: bool
  lane_change_control: bool
  route_speed_control: bool
  require_turn_signal: bool
  message_timeout_s: float
  turn_max_speed_mps: float

  @classmethod
  def read(cls, params: Params) -> NavAssistParams:
    timeout_ms = int(params.get("NavAssistMessageTimeoutMs", return_default=True))
    turn_max_kph = int(params.get("NavAssistTurnMaxSpeedKph", return_default=True))
    return cls(
      enabled=params.get_bool("NavAssistEnabled"),
      shadow_mode=params.get_bool("NavAssistShadowMode"),
      speed_control=params.get_bool("NavAssistSpeedControl"),
      turn_control=params.get_bool("NavAssistTurnControl"),
      lane_change_control=params.get_bool("NavAssistLaneChangeControl"),
      route_speed_control=params.get_bool("NavAssistRouteSpeedControl"),
      require_turn_signal=params.get_bool("NavAssistRequireTurnSignal"),
      message_timeout_s=max(0.2, min(timeout_ms / 1000.0, 10.0)),
      turn_max_speed_mps=max(5.0, min(turn_max_kph, 50)) * CV.KPH_TO_MS,
    )
