from openpilot.selfdrive.controls.lib.longitudinal_backends.registry import BackendId, get_backend
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.modes import get_longitudinal_planner_mode


ACTIVE_BACKEND_PARAM = "ActiveLongitudinalBackend"


def latch_active_backend(params) -> BackendId:
  """Latch one backend for an onroad session and preserve it across process restarts."""
  raw = params.get(ACTIVE_BACKEND_PARAM)
  if raw is not None:
    try:
      return get_backend(int(raw)).id
    except (TypeError, ValueError):
      pass

  desired = get_backend(get_longitudinal_planner_mode(params)).id
  params.put(ACTIVE_BACKEND_PARAM, str(int(desired)))
  return desired
