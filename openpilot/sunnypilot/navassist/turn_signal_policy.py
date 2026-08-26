from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from openpilot.sunnypilot.navassist.config import NavAssistParams
from openpilot.sunnypilot.navassist.types import Maneuver


class TurnSignalAction(StrEnum):
  NONE = "none"
  REQUEST = "request"
  CANCEL = "cancel"


@dataclass(frozen=True)
class TurnSignalDecision:
  action: TurnSignalAction = TurnSignalAction.NONE
  request_id: str = ""
  direction: str = ""
  reason: str = "idle"


class NavigationTurnSignalPolicy:
  """Requests Tesla turn signals; existing SP logic remains responsible for any lane change."""

  def __init__(self) -> None:
    self._consumed: tuple[str, int] | None = None

  @staticmethod
  def _direction(nav, nav_valid: bool) -> str:
    if not nav_valid:
      return ""
    maneuver = Maneuver(int(getattr(nav.maneuver, "raw", nav.maneuver)))
    if maneuver in (Maneuver.TURN_LEFT, Maneuver.FORK_LEFT):
      return "left"
    if maneuver in (Maneuver.TURN_RIGHT, Maneuver.FORK_RIGHT):
      return "right"
    return ""

  @staticmethod
  def _active_navigation_request(status: dict | None) -> bool:
    return bool(status is not None and status.get("origin") == "navigation")

  def update(self, nav, nav_valid: bool, params: NavAssistParams, car_state, car_control,
             controller_status: dict | None) -> TurnSignalDecision:
    direction = self._direction(nav, nav_valid)
    session_id = str(nav.sessionId) if nav_valid else ""
    maneuver_id = int(nav.maneuverId) if nav_valid else 0
    key = (session_id, maneuver_id)
    request_id = f"nav:{session_id}:{maneuver_id}"
    eligible = bool(
      params.enabled and params.turn_control and not params.shadow_mode
      and nav_valid and nav.dataValid and nav.guidanceValid and nav.guidanceActive
      and not nav.stale and not nav.offRoute and direction
    )

    if self._active_navigation_request(controller_status):
      same_request = controller_status.get("test_id") == request_id
      same_direction = controller_status.get("direction") == direction
      distance = float(nav.distanceToManeuverM) if nav_valid else 0.0
      if not eligible or not same_request or not same_direction or distance < 3.0:
        return TurnSignalDecision(TurnSignalAction.CANCEL, str(controller_status.get("test_id", "")),
                                  str(controller_status.get("direction", "")), "navigation_changed")
      return TurnSignalDecision(reason="active")

    # A manual validation session owns the CAN controller until it completes.
    if controller_status is not None:
      return TurnSignalDecision(reason="controller_busy")
    if not eligible:
      return TurnSignalDecision(reason="disabled_or_invalid")
    if self._consumed == key:
      return TurnSignalDecision(reason="consumed")
    if not car_control.latActive or car_state.brakePressed:
      return TurnSignalDecision(reason="control_gate")

    left = bool(car_state.leftBlinker)
    right = bool(car_state.rightBlinker)
    if left or right:
      # Never fight a physical stalk request, even when it already matches navigation.
      self._consumed = key
      return TurnSignalDecision(reason="driver_blinker")

    distance = float(nav.distanceToManeuverM)
    speed = max(float(car_state.vEgo), 0.0)
    trigger_distance = min(180.0, max(20.0, speed * 6.0))
    if not 3.0 <= distance <= trigger_distance:
      return TurnSignalDecision(reason="window")
    return TurnSignalDecision(TurnSignalAction.REQUEST, request_id, direction, "triggered")

  def mark_submitted(self, nav) -> None:
    self._consumed = (str(nav.sessionId), int(nav.maneuverId))
