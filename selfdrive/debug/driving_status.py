"""Read-only live driving status for the local settings web UI."""
import threading
import time

from cereal import messaging
from openpilot.common.params import Params


SERVICES = ("carState", "selfdriveState", "selfdriveStateSP", "modelV2")
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
      leads.append({"x": _number(lead.x[0]), "y": _number(lead.y[0], 2), "velocity_mps": _number(lead.v[0]), "probability": _number(lead.prob, 2)})
  return {
    "path": _line_points(model.position),
    # The inner pair is the current-lane boundary and is the clearest signal on a compact display.
    "lanes": [_line_points(line) for line in list(model.laneLines)[1:3]],
    "edges": [_line_points(line) for line in model.roadEdges],
    "leads": leads,
    "lane_change": str(model.meta.laneChangeState),
    "lane_change_direction": str(model.meta.laneChangeDirection),
    "hard_brake_predicted": bool(model.meta.hardBrakePredicted),
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
      model = self.sm["modelV2"]

      alert = " ".join(text for text in (selfdrive_state.alertText1, selfdrive_state.alertText2) if text)
      cruise_speed = max(float(car_state.vCruiseCluster), float(car_state.cruiseState.speedCluster)) * 3.6
      return {
        "onroad": self.params.get_bool("IsOnroad"),
        "connected": {service: self.sm.alive[service] for service in SERVICES},
        "speed_kph": _number(car_state.vEgo * 3.6),
        "set_speed_kph": _number(cruise_speed),
        "openpilot_enabled": bool(selfdrive_state.enabled),
        "mads_enabled": bool(sp_state.mads.enabled),
        "alert": alert,
        "geometry": _model_geometry(model),
        "updated_at": int(time.time()),
      }


_STATUS = DrivingStatus()


def driving_status_snapshot() -> dict[str, object]:
  return _STATUS.snapshot()
