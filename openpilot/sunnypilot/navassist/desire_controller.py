from __future__ import annotations

from dataclasses import dataclass

from openpilot.sunnypilot.navassist.config import NavAssistParams
from openpilot.sunnypilot.navassist.types import LateralRequest, Maneuver


@dataclass(frozen=True)
class NavDesireOutput:
  request: LateralRequest = LateralRequest.NONE
  would_request: LateralRequest = LateralRequest.NONE
  reason: str = "idle"


class NavDesireController:
  """One-shot, driver-confirmed navigation turn request."""

  def __init__(self) -> None:
    self._consumed: tuple[str, int] | None = None

  def update(self, nav, nav_valid: bool, params: NavAssistParams, carstate, lateral_active: bool) -> NavDesireOutput:
    raw_maneuver = getattr(nav.maneuver, "raw", nav.maneuver) if nav_valid else 0
    maneuver = Maneuver(int(raw_maneuver))
    request = {
      Maneuver.TURN_LEFT: LateralRequest.TURN_LEFT,
      Maneuver.TURN_RIGHT: LateralRequest.TURN_RIGHT,
    }.get(maneuver, LateralRequest.NONE)
    if request == LateralRequest.NONE:
      return NavDesireOutput(reason="unsupported")

    key = (str(nav.sessionId), int(nav.maneuverId))
    if not params.enabled or not params.turn_control:
      return NavDesireOutput(would_request=request, reason="disabled")
    if params.shadow_mode:
      return NavDesireOutput(would_request=request, reason="shadow")
    if not nav_valid or not nav.dataValid or nav.stale or nav.offRoute:
      return NavDesireOutput(reason="invalid")
    if self._consumed == key:
      return NavDesireOutput(reason="consumed")
    if not lateral_active or carstate.brakePressed or carstate.trailerConnected:
      self._consumed = key if carstate.brakePressed else self._consumed
      return NavDesireOutput(would_request=request, reason="driver_gate")
    if carstate.vEgo > params.turn_max_speed_mps:
      return NavDesireOutput(would_request=request, reason="speed")
    distance = float(nav.distanceToManeuverM)
    time_to_maneuver = distance / max(float(carstate.vEgo), 3.0)
    if not (15.0 <= distance <= 80.0 and time_to_maneuver <= 6.0):
      return NavDesireOutput(would_request=request, reason="window")
    confirmed = (
      request == LateralRequest.TURN_LEFT and carstate.leftBlinker and not carstate.rightBlinker
      or request == LateralRequest.TURN_RIGHT and carstate.rightBlinker and not carstate.leftBlinker
    )
    if params.require_turn_signal and not confirmed:
      if carstate.leftBlinker or carstate.rightBlinker:
        self._consumed = key
      return NavDesireOutput(would_request=request, reason="turn_signal")
    self._consumed = key
    return NavDesireOutput(request=request, would_request=request, reason="triggered")
