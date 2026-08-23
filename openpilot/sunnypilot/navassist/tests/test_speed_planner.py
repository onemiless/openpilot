import math

from openpilot.sunnypilot.navassist.speed_planner import select_speed_candidate
from openpilot.sunnypilot.navassist.types import SpeedCandidate, SpeedSource


def test_selects_lowest_finite_target():
  selected = select_speed_candidate([
    SpeedCandidate(SpeedSource.MANEUVER, 8.0, 50.0),
    SpeedCandidate(SpeedSource.SPEED_CAMERA, 10.0, 20.0),
  ])
  assert selected is not None and selected.source == SpeedSource.MANEUVER


def test_rejects_zero_nan_and_invalid_distance():
  assert select_speed_candidate([
    SpeedCandidate(SpeedSource.MANEUVER, 0.0, 10.0),
    SpeedCandidate(SpeedSource.ROUTE_CURVE, math.nan, 10.0),
    SpeedCandidate(SpeedSource.SECTION, 5.0, -1.0),
  ]) is None
