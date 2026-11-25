"""Driver-monitoring choice latched once by manager for each driving session."""
from openpilot.common.params import Params
from openpilot.common.hardware import HARDWARE
from openpilot.sunnypilot.hardware.profile import has_driver_camera


def driver_monitoring_default() -> bool:
  return has_driver_camera() and HARDWARE.get_device_type() == "mici"


def driver_monitoring_configured(params: Params) -> bool:
  configured = params.get("DriverMonitoringEnabled")
  if configured is None:
    configured = driver_monitoring_default()
  return has_driver_camera() and bool(configured)


def driver_monitoring_enabled(params: Params | None = None) -> bool:
  params = Params() if params is None else params
  active = params.get("ActiveDriverMonitoringEnabled")
  return driver_monitoring_configured(params) if active is None else has_driver_camera() and bool(active)


def latch_driver_monitoring(params: Params) -> bool:
  enabled = driver_monitoring_enabled(params)
  if params.get("ActiveDriverMonitoringEnabled") is None:
    params.put_bool("ActiveDriverMonitoringEnabled", enabled, block=True)
  if not enabled:
    params.remove("DriverTooDistracted")
    params.remove("Offroad_DriverMonitoringUncertain")
  return enabled
