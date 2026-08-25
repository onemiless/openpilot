from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class Maneuver(IntEnum):
  NONE = 0
  TURN_LEFT = 1
  TURN_RIGHT = 2
  FORK_LEFT = 3
  FORK_RIGHT = 4
  ROUNDABOUT = 5
  UTURN = 6
  ARRIVE = 7
  TOLLGATE = 8


class SpeedSource(IntEnum):
  NONE = 0
  MANEUVER = 1
  NEXT_MANEUVER = 2
  SPEED_CAMERA = 3
  SECTION = 4
  ROUTE_CURVE = 5


class InvalidReason(IntEnum):
  NONE = 0
  DISABLED = 1
  DISCONNECTED = 2
  STALE_MESSAGE = 3
  PROTOCOL_ERROR = 4
  SEQUENCE_ERROR = 5
  NAVIGATION_INACTIVE = 6
  OFF_ROUTE = 7
  LOCATION_INVALID = 8


class NavSource(IntEnum):
  NONE = 0
  CARROT_V2 = 1
  AMAP_COMPANION_V1 = 2


class LateralRequest(IntEnum):
  NONE = 0
  TURN_LEFT = 1
  TURN_RIGHT = 2
  FORK_LEFT = 3
  FORK_RIGHT = 4


@dataclass(frozen=True)
class StreamRecord:
  present: bool = False
  sequence: int = 0
  received_mono_ns: int = 0
  value: object | None = None
  reason: str = ""
  source_timestamp_ms: int = 0
  sent_at_ms: int = 0


@dataclass(frozen=True)
class ProtocolSnapshot:
  connected: bool = False
  session_id: str = ""
  generation: int = 0
  records: dict[str, StreamRecord] | None = None
  protocol_error: str = ""
  sequence_error: bool = False
  source: NavSource = NavSource.NONE

  def record(self, name: str) -> StreamRecord:
    return (self.records or {}).get(name, StreamRecord())


@dataclass(frozen=True)
class SpeedCandidate:
  source: SpeedSource
  target_speed_mps: float
  control_distance_m: float


@dataclass(frozen=True)
class NavAssistState:
  connected: bool = False
  session_id: str = ""
  generation: int = 0
  data_valid: bool = False
  guidance_valid: bool = False
  speed_valid: bool = False
  route_valid: bool = False
  guidance_active: bool = False
  off_route: bool = False
  stale: bool = True
  invalid_reason: InvalidReason = InvalidReason.DISCONNECTED
  maneuver: Maneuver = Maneuver.NONE
  maneuver_id: int = 0
  raw_turn_type: int = -1
  distance_to_maneuver_m: float = 0.0
  maneuver_target_speed_mps: float = 0.0
  next_maneuver: Maneuver = Maneuver.NONE
  next_maneuver_id: int = 0
  raw_next_turn_type: int = -1
  distance_to_next_maneuver_m: float = 0.0
  road_limit_mps: float = 0.0
  route_speed_mps: float = 0.0
  speed_camera_mps: float = 0.0
  speed_camera_distance_m: float = 0.0
  section_speed_mps: float = 0.0
  section_distance_m: float = 0.0
  desired_speed_mps: float = 0.0
  speed_control_distance_m: float = 0.0
  speed_source: SpeedSource = SpeedSource.NONE
  route_deviation_m: float = 0.0
  source: NavSource = NavSource.NONE
