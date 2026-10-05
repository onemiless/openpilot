"""Tesla PCM cruise confirmation steps, separate from stock ACC ownership."""

# Tesla PCM longitudinal confirms SLA through the displayed cruise set speed.
# Keep the upstream fixed maximum for other brands, while Tesla follows the
# actual detected limit in the same discrete steps exposed by its cruise UI.
TESLA_PCM_LONG_REQUIRED_MAX_SET_SPEED = {
  True: tuple((speed, speed / 3.6) for speed in range(20, 131, 10)),
  False: tuple((speed, speed * 0.44704) for speed in range(15, 91, 5)),
}

def required_cruise_speed(metric: bool, limit_conv: int, has_speed_limit: bool) -> float:
  segments = TESLA_PCM_LONG_REQUIRED_MAX_SET_SPEED[metric]
  if not has_speed_limit:
    return segments[-1][1]
  return next((value for threshold, value in segments if limit_conv <= threshold), segments[-1][1])
