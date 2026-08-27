from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from openpilot.sunnypilot.navassist.config import NavAssistParams
from openpilot.sunnypilot.navassist.types import Maneuver


TURN_SIGNAL_LEAD_TIME_S = 10.0
TURN_SIGNAL_MIN_DISTANCE_M = 50.0
TURN_SIGNAL_MAX_DISTANCE_M = 250.0
TURN_SIGNAL_RETRY_DELAY_NS = 1_000_000_000
TURN_SIGNAL_MAX_ATTEMPTS = 3


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
    self._key: tuple[str, int] | None = None
    self._attempts = 0
    self._active_request_id = ""
    self._retry_after_ns = 0
    self._consumed = False

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

  def _select_key(self, key: tuple[str, int]) -> None:
    if key == self._key:
      return
    self._key = key
    self._attempts = 0
    self._active_request_id = ""
    self._retry_after_ns = 0
    self._consumed = False

  def update(self, nav, nav_valid: bool, params: NavAssistParams, car_state, lateral_ready: bool,
             controller_status: dict | None, now_ns: int) -> TurnSignalDecision:
    direction = self._direction(nav, nav_valid)
    session_id = str(nav.sessionId) if nav_valid else ""
    maneuver_id = int(nav.maneuverId) if nav_valid else 0
    key = (session_id, maneuver_id)
    self._select_key(key)
    request_id = f"nav:{session_id}:{maneuver_id}:{self._attempts + 1}"
    eligible = bool(
      params.enabled and params.turn_control and not params.shadow_mode
      and nav_valid and nav.dataValid and nav.guidanceValid and nav.guidanceActive
      and not nav.stale and not nav.offRoute and direction
    )

    if self._active_navigation_request(controller_status):
      same_request = controller_status.get("test_id") == self._active_request_id
      same_direction = controller_status.get("direction") == direction
      distance = float(nav.distanceToManeuverM) if nav_valid else 0.0
      if not eligible or not same_request or not same_direction or distance < 3.0:
        return TurnSignalDecision(TurnSignalAction.CANCEL, str(controller_status.get("test_id", "")),
                                  str(controller_status.get("direction", "")), "navigation_changed")
      return TurnSignalDecision(reason="active")

    # A manual validation session owns the CAN controller until it completes.
    if controller_status is not None:
      return TurnSignalDecision(reason="controller_busy")
    if self._active_request_id:
      return TurnSignalDecision(reason="awaiting_completion")
    if not eligible:
      return TurnSignalDecision(reason="disabled_or_invalid")
    if self._consumed:
      return TurnSignalDecision(reason="consumed")
    if self._attempts >= TURN_SIGNAL_MAX_ATTEMPTS:
      return TurnSignalDecision(reason="attempts_exhausted")
    if now_ns < self._retry_after_ns:
      return TurnSignalDecision(reason="retry_wait")
    if not lateral_ready or car_state.brakePressed:
      return TurnSignalDecision(reason="control_gate")

    left = bool(car_state.leftBlinker)
    right = bool(car_state.rightBlinker)
    if left or right:
      # Never fight a physical stalk request, even when it already matches navigation.
      self._consumed = True
      return TurnSignalDecision(reason="driver_blinker")

    distance = float(nav.distanceToManeuverM)
    speed = max(float(car_state.vEgo), 0.0)
    trigger_distance = min(TURN_SIGNAL_MAX_DISTANCE_M,
                           max(TURN_SIGNAL_MIN_DISTANCE_M, speed * TURN_SIGNAL_LEAD_TIME_S))
    if not 3.0 <= distance <= trigger_distance:
      return TurnSignalDecision(reason="window")
    return TurnSignalDecision(TurnSignalAction.REQUEST, request_id, direction, "triggered")

  def mark_submitted(self, nav, request_id: str, now_ns: int) -> None:
    self._select_key((str(nav.sessionId), int(nav.maneuverId)))
    self._attempts += 1
    self._active_request_id = request_id
    self._retry_after_ns = int(now_ns)

  def complete(self, result: dict, now_ns: int) -> None:
    if not self._active_request_id or result.get("test_id") != self._active_request_id:
      return
    self._active_request_id = ""
    lane_change_started = bool(result.get("lane_change_started", False))
    retryable_cancel = result.get("cancel_reason") in ("session_timeout", "action_panda_rejected")
    if not lane_change_started and retryable_cancel and self._attempts < TURN_SIGNAL_MAX_ATTEMPTS:
      self._retry_after_ns = int(now_ns) + TURN_SIGNAL_RETRY_DELAY_NS
    else:
      self._consumed = True
