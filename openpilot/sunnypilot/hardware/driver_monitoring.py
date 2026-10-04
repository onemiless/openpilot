"""Driver-monitoring choice latched once by manager for each driving session."""
from openpilot.common.params import Params
from openpilot.sunnypilot.hardware.profile import has_driver_camera


def driver_monitoring_enabled(params: Params | None = None) -> bool:
  params = Params() if params is None else params
  active = params.get("ActiveDriverMonitoringEnabled")
  configured = params.get("DriverMonitoringEnabled", return_default=True) if active is None else active
  return has_driver_camera() and bool(configured)


def latch_driver_monitoring(params: Params) -> bool:
  enabled = driver_monitoring_enabled(params)
  if params.get("ActiveDriverMonitoringEnabled") is None:
    params.put_bool("ActiveDriverMonitoringEnabled", enabled, block=True)
  if not enabled:
    params.remove("DriverTooDistracted")
    params.remove("Offroad_DriverMonitoringUncertain")
  return enabled
