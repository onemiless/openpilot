"""Read-only live driving status for the local settings web UI."""
import threading
import time

from cereal import messaging
from openpilot.common.params import Params


SERVICES = ("carState", "controlsState", "selfdriveState", "selfdriveStateSP", "deviceState", "modelV2")
MAX_TRAJECTORY_DISTANCE_M = 100.0
TRAJECTORY_STRIDE = 3


def _number(value: object, digits: int = 1) -> float:
  return round(float(value), digits)


def _line_points(line: object) -> list[list[float]]:
  """Compact model coordinates for browser-side rendering."""
  xs, ys = list(line.x), list(line.y)
  points = []
  for index in range(0, min(len(xs), len(ys)), TRAJECTORY_STRIDE):
    x = float(xs[index])
    if 0.0 <= x <= MAX_TRAJECTORY_DISTANCE_M:
      points.append([_number(x), _number(ys[index], 2)])
  return points


def _model_geometry(model: object) -> dict[str, object]:
  leads = []
  for lead in model.leadsV3:
    if lead.prob >= 0.5 and len(lead.x) and len(lead.y):
      leads.append({"x": _number(lead.x[0]), "y": _number(lead.y[0], 2), "probability": _number(lead.prob, 2)})
  return {
    "path": _line_points(model.position),
    # The inner pair is the current-lane boundary and is the clearest signal on a compact display.
    "lanes": [_line_points(line) for line in list(model.laneLines)[1:3]],
    "edges": [_line_points(line) for line in model.roadEdges],
    "leads": leads,
  }


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
      model = self.sm["modelV2"]

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
        "power_draw_w": _number(device_state.powerDrawW),
        "temperature_c": _number(max(temperatures)) if temperatures else None,
        "geometry": _model_geometry(model),
        "updated_at": int(time.time()),
      }


_STATUS = DrivingStatus()


def driving_status_snapshot() -> dict[str, object]:
  return _STATUS.snapshot()
