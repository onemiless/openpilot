"""Read-only live driving status for the local settings web UI."""
import threading
import time

from cereal import messaging
from openpilot.common.params import Params


SERVICES = ("carState", "controlsState", "selfdriveState", "selfdriveStateSP", "deviceState")


def _number(value: object, digits: int = 1) -> float:
  return round(float(value), digits)


class DrivingStatus:
  def __init__(self) -> None:
    self.params = Params()
    self.sm = messaging.SubMaster(SERVICES)
    self.lock = threading.Lock()

  def snapshot(self) -> dict[str, object]:
    with self.lock:
      self.sm.update(0)
      car_state = self.sm["carState"]
      selfdrive_state = self.sm["selfdriveState"]
      sp_state = self.sm["selfdriveStateSP"]
      device_state = self.sm["deviceState"]

      alert = " ".join(text for text in (selfdrive_state.alertText1, selfdrive_state.alertText2) if text)
      cruise_speed = max(float(car_state.vCruiseCluster), float(car_state.cruiseState.speedCluster)) * 3.6
      temperatures = list(device_state.cpuTempC) + list(device_state.gpuTempC)
      return {
        "onroad": self.params.get_bool("IsOnroad"),
        "connected": {service: self.sm.alive[service] for service in SERVICES},
        "speed_kph": _number(car_state.vEgo * 3.6),
        "set_speed_kph": _number(cruise_speed),
        "acceleration": _number(car_state.aEgo, 2),
        "steering_angle_deg": _number(car_state.steeringAngleDeg),
        "steering_pressed": bool(car_state.steeringPressed),
        "gas_pressed": bool(car_state.gasPressed),
        "brake_pressed": bool(car_state.brakePressed),
        "standstill": bool(car_state.standstill),
        "openpilot_enabled": bool(selfdrive_state.enabled),
        "mads_enabled": bool(sp_state.mads.enabled),
        "experimental_mode": bool(selfdrive_state.experimentalMode),
        "alert": alert,
        "battery_percent": _number(device_state.batteryPercent),
        "temperature_c": _number(max(temperatures)) if temperatures else None,
        "updated_at": int(time.time()),
      }


_STATUS = DrivingStatus()


def driving_status_snapshot() -> dict[str, object]:
  return _STATUS.snapshot()
