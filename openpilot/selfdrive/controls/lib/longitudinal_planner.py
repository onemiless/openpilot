from importlib import import_module

from openpilot.common.params import Params
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.modes import LONGITUDINAL_PLANNER_OFFICIAL, get_longitudinal_planner_mode


def get_planner_class(mode):
  module_name = ("openpilot.selfdrive.controls.lib.longitudinal_planner_official"
                 if mode == LONGITUDINAL_PLANNER_OFFICIAL else
                 "openpilot.selfdrive.controls.lib.longitudinal_planner_local")
  return import_module(module_name).LongitudinalPlanner


class LongitudinalPlanner:
  """Construct one complete planner implementation for the lifetime of plannerd."""

  def __new__(cls, *args, **kwargs):
    return get_planner_class(get_longitudinal_planner_mode(Params()))(*args, **kwargs)
