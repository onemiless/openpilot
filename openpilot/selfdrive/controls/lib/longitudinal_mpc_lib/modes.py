LONGITUDINAL_PLANNER_OFFICIAL = 0
LONGITUDINAL_PLANNER_LOCAL = 1
LONGITUDINAL_PLANNER_TN = 2

LONGITUDINAL_PLANNER_LABELS = {
  LONGITUDINAL_PLANNER_OFFICIAL: "SP Upstream Tunable",
  LONGITUDINAL_PLANNER_LOCAL: "Local",
  LONGITUDINAL_PLANNER_TN: "TN-NoDEC",
}


def get_longitudinal_planner_mode(params) -> int:
  try:
    mode = int(params.get("LongitudinalPlannerMode", return_default=True))
  except (TypeError, ValueError):
    mode = LONGITUDINAL_PLANNER_OFFICIAL
  return mode if mode in LONGITUDINAL_PLANNER_LABELS else LONGITUDINAL_PLANNER_OFFICIAL
