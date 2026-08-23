from __future__ import annotations

import math

from openpilot.sunnypilot.navassist.types import SpeedCandidate


SOURCE_PRIORITY = {
  1: 0,  # maneuver
  2: 1,  # next maneuver
  3: 2,  # camera
  4: 3,  # section
  5: 4,  # route curve
}


def select_speed_candidate(candidates: list[SpeedCandidate]) -> SpeedCandidate | None:
  valid = [c for c in candidates if (
    math.isfinite(c.target_speed_mps) and c.target_speed_mps > 0.0
    and math.isfinite(c.control_distance_m) and c.control_distance_m >= 0.0
  )]
  if not valid:
    return None
  return min(valid, key=lambda c: (c.target_speed_mps, c.control_distance_m, SOURCE_PRIORITY.get(int(c.source), 99)))
