import fcntl

from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_backends.registry import BackendId, BackendSpec, get_backend


DESIRED_BACKEND_PARAM = "LongitudinalPlannerMode"
ACTIVE_BACKEND_PARAM = "ActiveLongitudinalBackend"
BACKEND_LOCK_PATH = "/tmp/longitudinal_backend_session.lock"


def latch_active_backend(params) -> BackendSpec:
  """Select one installed provider for the lifetime of an onroad session."""
  # A one-time startup lock covers both reads and the durable typed write.
  # Individual Params operations are atomic, the read/select/write sequence is not.
  with open(BACKEND_LOCK_PATH, "a") as lock_file:
    fcntl.flock(lock_file, fcntl.LOCK_EX)
    active = params.get(ACTIVE_BACKEND_PARAM)
    if active is not None:
      return get_backend(active)

    backend = get_backend(params.get(DESIRED_BACKEND_PARAM, return_default=True))
    params.put(ACTIVE_BACKEND_PARAM, int(backend.id), block=True)
    return backend


def active_backend_id(params) -> BackendId:
  return latch_active_backend(params).id


def end_longitudinal_session(params, consumers) -> None:
  """Join all old latch writers before clearing the completed session."""
  consumers = tuple(consumers)
  for process in consumers:
    process.stop(block=False)
  for process in consumers:
    process.stop(block=True)
  # Never hold this lock while stopping: a gracefully exiting consumer may
  # still need it to finish its startup write. Join/SIGKILL closes that window.
  with open(BACKEND_LOCK_PATH, "a") as lock_file:
    fcntl.flock(lock_file, fcntl.LOCK_EX)
    params.remove(ACTIVE_BACKEND_PARAM)
