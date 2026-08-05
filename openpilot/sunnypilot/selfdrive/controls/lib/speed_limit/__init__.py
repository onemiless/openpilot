"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
LIMIT_ADAPT_ACC = -1.  # m/s^2 Ideal acceleration for the adapting (braking) phase when approaching speed limits.
LIMIT_MAX_MAP_DATA_AGE = 10.  # s Maximum time to hold to map data, then consider it invalid inside limits controllers.

# Speed Limit Assist constants
# Mapping of (threshold speed in unit system, max PCM set speed in m/s),
# ordered by ascending thresholds. Tesla PCM longitudinal uses the cruise set
# speed as the SLA confirmation value, so the requested value must follow the
# actual speed limit instead of always jumping to 120/130 km/h.
PCM_LONG_REQUIRED_MAX_SET_SPEED = {
  True: tuple((speed, speed / 3.6) for speed in range(20, 131, 10)),
  False: tuple((speed, speed * 0.44704) for speed in range(15, 91, 5)),
}

CONFIRM_SPEED_THRESHOLD = {
  True: 80,   # km/h
  False: 50,  # mph
}


def resolve_pcm_long_required_max(metric: bool, limit_conv: int, has_speed_limit: bool) -> float:
  segments = PCM_LONG_REQUIRED_MAX_SET_SPEED[metric]
  if not has_speed_limit:
    return segments[-1][1]

  for threshold, value in segments:
    if limit_conv <= threshold:
      return value
  return segments[-1][1]
