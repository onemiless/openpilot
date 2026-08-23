from __future__ import annotations

from openpilot.sunnypilot.navassist.types import Maneuver


TURN_TYPE_MAP = {
  12: Maneuver.TURN_LEFT, 16: Maneuver.TURN_LEFT,
  13: Maneuver.TURN_RIGHT, 19: Maneuver.TURN_RIGHT,
  7: Maneuver.FORK_LEFT, 17: Maneuver.FORK_LEFT, 44: Maneuver.FORK_LEFT,
  75: Maneuver.FORK_LEFT, 76: Maneuver.FORK_LEFT, 102: Maneuver.FORK_LEFT,
  105: Maneuver.FORK_LEFT, 112: Maneuver.FORK_LEFT, 115: Maneuver.FORK_LEFT,
  118: Maneuver.FORK_LEFT,
  6: Maneuver.FORK_RIGHT, 43: Maneuver.FORK_RIGHT, 73: Maneuver.FORK_RIGHT,
  74: Maneuver.FORK_RIGHT, 101: Maneuver.FORK_RIGHT, 104: Maneuver.FORK_RIGHT,
  111: Maneuver.FORK_RIGHT, 114: Maneuver.FORK_RIGHT, 117: Maneuver.FORK_RIGHT,
  123: Maneuver.FORK_RIGHT, 124: Maneuver.FORK_RIGHT,
  14: Maneuver.UTURN,
  153: Maneuver.TOLLGATE, 154: Maneuver.TOLLGATE, 249: Maneuver.TOLLGATE,
  201: Maneuver.ARRIVE,
  **dict.fromkeys(range(131, 143), Maneuver.ROUNDABOUT),
}


def map_turn_type(raw: object) -> Maneuver:
  if isinstance(raw, bool) or not isinstance(raw, int):
    return Maneuver.NONE
  return TURN_TYPE_MAP.get(raw, Maneuver.NONE)
