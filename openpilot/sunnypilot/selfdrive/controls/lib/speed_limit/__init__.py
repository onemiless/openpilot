"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from openpilot.sunnypilot.selfdrive.car.tesla.speed_limit_policy import (
  TESLA_PCM_LONG_REQUIRED_MAX_SET_SPEED as TESLA_PCM_LONG_REQUIRED_MAX_SET_SPEED,
  required_cruise_speed,
)

LIMIT_ADAPT_ACC = -1.  # m/s^2 Ideal acceleration for the adapting (braking) phase when approaching speed limits.
LIMIT_MAX_MAP_DATA_AGE = 10.  # s Maximum time to hold to map data, then consider it invalid inside limits controllers.

# Speed Limit Assist constants
PCM_LONG_REQUIRED_MAX_SET_SPEED = {
  True: (33.3333, 36.1111),  # km/h, (120, 130)
  False: (31.2928, 35.7632),  # mph, (70, 80)
}

CONFIRM_SPEED_THRESHOLD = {
  True: 80,   # km/h
  False: 50,  # mph
}


def resolve_pcm_long_required_max(metric: bool, limit_conv: int, has_speed_limit: bool, *, brand: str) -> float:
  if brand != "tesla":
    cst_low, cst_high = PCM_LONG_REQUIRED_MAX_SET_SPEED[metric]
    return cst_low if has_speed_limit and limit_conv < CONFIRM_SPEED_THRESHOLD[metric] else cst_high

  return required_cruise_speed(metric, limit_conv, has_speed_limit)
