from importlib import import_module

from openpilot.common.params import Params
from openpilot.selfdrive.controls.lib.longitudinal_backends.registry import get_backend
from openpilot.selfdrive.controls.lib.longitudinal_backends.session import latch_active_backend
from openpilot.selfdrive.controls.lib.longitudinal_backends.tuning import migrate_legacy_config


def get_planner_class(mode):
  return import_module(get_backend(mode).planner_module).LongitudinalPlanner


class LongitudinalPlanner:
  """Construct one complete planner implementation for the lifetime of plannerd."""

  def __new__(cls, *args, **kwargs):
    params = Params()
    migrate_legacy_config(params)
    backend_id = latch_active_backend(params)
    planner = get_planner_class(backend_id)(*args, **kwargs)
    planner.active_backend_id = backend_id
    return planner
