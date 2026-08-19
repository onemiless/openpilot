import math
import time

from opendbc.car import structs
from opendbc.car.tesla.ars408_can import ARS408CAN, ARS408_FILTER_SIGNALS, ARS408_MOTION_INPUT_ENABLED
from opendbc.car.tesla.ars408_log import get_ars408_logger
from opendbc.car.vehicle_model import VehicleModel
from openpilot.common.params import Params


log = get_ars408_logger("card")

ARS408_REQUEST_TTL_MS = 30 * 60 * 1000


def calculate_yaw_rate(vehicle_model, speed_mps, steering_angle_deg):
  """Estimate ARS408 yaw rate without changing stock CarState semantics."""
  if not math.isfinite(speed_mps) or not math.isfinite(steering_angle_deg) or abs(speed_mps) < 0.05:
    return 0.0
  curvature = -vehicle_model.calc_curvature(math.radians(steering_angle_deg), abs(speed_mps), 0.0)
  return float(curvature * abs(speed_mps))


class ARS408Controller:
  """Owns external ARS408 configuration and ego-motion CAN output."""

  def __init__(self, CP):
    self.can = ARS408CAN()
    self.VM = VehicleModel(CP)
    self.params = Params()
    self.motion_enabled = self.params.get_bool("TeslaRadarMotionInput")
    self.motion_valid_prev = None
    self.config_request = None
    self.filter_request = None
    self.last_heartbeat = None
    self.last_standstill = None
    self.last_controls_enabled = None
    log.info("ARS408 controller configured motion_enabled=%d bus=1 rate_hz=20", int(self.motion_enabled))

  def _motion_sends(self, CS):
    if not ARS408_MOTION_INPUT_ENABLED:
      return []

    enabled = self.params.get_bool("TeslaRadarMotionInput")
    if enabled != self.motion_enabled:
      self.motion_enabled = enabled
      self.motion_valid_prev = None
      log.info("ARS408 motion input runtime enabled=%d", int(enabled))
    if not enabled:
      return []

    speed_mps = float(CS.out.vEgoRaw)
    yaw_rate_rad_s = calculate_yaw_rate(self.VM, speed_mps, float(CS.out.steeringAngleDeg))
    motion_valid = bool(CS.out.canValid) and math.isfinite(speed_mps) and math.isfinite(yaw_rate_rad_s)
    if motion_valid != self.motion_valid_prev:
      log.info("ARS408 motion source valid=%d speed=%.3f yaw_rate_rad_s=%.4f",
               int(motion_valid), speed_mps, yaw_rate_rad_s)
      self.motion_valid_prev = motion_valid
    if not motion_valid:
      return []

    reverse = CS.out.gearShifter == structs.CarState.GearShifter.reverse
    standstill = CS.out.standstill or abs(speed_mps) < 0.05
    direction = 0 if standstill else (2 if reverse else 1)
    yaw_rate_deg_s = math.degrees(-yaw_rate_rad_s if reverse else yaw_rate_rad_s)
    return [
      self.can.create_speed_information(speed_mps, direction),
      self.can.create_yaw_rate_information(yaw_rate_deg_s),
    ]

  @staticmethod
  def _parse_config_request(raw):
    request_id, field, value, store = raw.split(",", 3)
    if field not in ("max_distance", "send_extended", "output_type"):
      raise ValueError(f"unsupported field {field}")
    value, store = int(value), int(store)
    if store not in (0, 1):
      raise ValueError("store must be 0 or 1")
    return {"id": request_id, "field": field, "value": value, "store": bool(store),
            "sent": False, "confirmed": False, "sent_frame": 0, "state_seq": 0}

  @staticmethod
  def _parse_filter_request(raw):
    parts = raw.split(",")
    if len(parts) == 3:
      request_id, action, index = parts
      if action != "query":
        raise ValueError(f"unsupported filter action {action}")
      return {"id": request_id, "index": int(index), "query_only": True, "phase": "query",
              "sent": False, "sent_frame": 0, "state_seq": 0}
    if len(parts) != 5:
      raise ValueError("filter request must be query or one complete record")
    request_id, index, active, minimum, maximum = parts
    active = int(active)
    if active not in (0, 1):
      raise ValueError("active must be 0 or 1")
    return {"id": request_id, "index": int(index), "active": bool(active),
            "minimum": float(minimum), "maximum": float(maximum), "query_only": False,
            "phase": "query", "sent": False, "sent_frame": 0, "state_seq": 0}

  @staticmethod
  def _request_expired(request_id, now_ms=None):
    created_ms = int(request_id)
    age_ms = (int(time.monotonic() * 1000) if now_ms is None else now_ms) - created_ms
    return age_ms < 0 or age_ms > ARS408_REQUEST_TTL_MS

  def _request(self, key):
    raw = self._text_param(key)
    return raw.strip() if raw else None

  def _clear_request(self, key, request_id):
    raw = self._request(key)
    if raw is not None and raw.split(",", 1)[0] == str(request_id):
      self.params.remove(key)

  def _text_param(self, key):
    raw = self.params.get(key)
    if isinstance(raw, bytes):
      return raw.decode("utf8", errors="replace")
    return None if raw is None else str(raw)

  def _state_seq(self, key):
    raw = self.params.get(key)
    try:
      return int(raw) if raw is not None else 0
    except (TypeError, ValueError):
      return 0

  def _publish_config_result(self, request_id, status, detail=""):
    self.params.put_nonblocking("TeslaRadarConfigResult", f"{request_id},{status},{detail}")

  def _publish_filter_result(self, request_id, status, detail=""):
    self.params.put_nonblocking("TeslaRadarFilterResult", f"{request_id},{status},{detail}")

  def _publish_apply_state(self, CC, CS):
    now = int(time.monotonic())
    standstill = bool(CS.out.standstill) and abs(float(CS.out.vEgoRaw)) < 0.1
    controls_enabled = bool(CC.enabled)
    if now != self.last_heartbeat:
      self.params.put_int_nonblocking("TeslaRadarApplyHeartbeat", now)
      self.last_heartbeat = now
    if standstill != self.last_standstill:
      self.params.put_bool_nonblocking("TeslaRadarVehicleStandstill", standstill)
      self.last_standstill = standstill
    if controls_enabled != self.last_controls_enabled:
      self.params.put_bool_nonblocking("TeslaRadarControlsEnabled", controls_enabled)
      self.last_controls_enabled = controls_enabled

  @staticmethod
  def _write_block_reason(CC, CS):
    if not CS.out.canValid:
      return "wait for valid CAN"
    if bool(CC.enabled):
      return "openpilot must be disengaged"
    if not bool(CS.out.standstill) or abs(float(CS.out.vEgoRaw)) >= 0.1:
      return "vehicle must be stationary"
    return None

  def _config_matches(self, request):
    state_keys = {
      "max_distance": "TeslaRadarStateMaxDistance",
      "send_extended": "TeslaRadarStateExtended",
      "output_type": "TeslaRadarStateOutputType",
    }
    raw = self.params.get(state_keys[request["field"]])
    return raw is not None and int(raw) == request["value"]

  @staticmethod
  def _parse_filter_state(raw_state):
    index, active, minimum, maximum = raw_state.split(",", 3)
    return int(index), bool(int(active)), float(minimum), float(maximum)

  @staticmethod
  def _filter_matches(request, state):
    index, active, minimum, maximum = state
    resolution = ARS408_FILTER_SIGNALS[request["index"]][3]
    return index == request["index"] and active == request["active"] and \
      math.isclose(minimum, request["minimum"], abs_tol=resolution / 2 + 1e-6) and \
      math.isclose(maximum, request["maximum"], abs_tol=resolution / 2 + 1e-6)

  def _load_next_request(self):
    if self.config_request is not None or self.filter_request is not None:
      return
    raw_config = self._request("TeslaRadarConfigRequest")
    raw_filter = None if raw_config else self._request("TeslaRadarFilterRequest")
    try:
      if raw_config:
        request = self._parse_config_request(raw_config)
        if self._request_expired(request["id"]):
          self._publish_config_result(request["id"], "expired", "request timestamp is invalid or expired")
          self._clear_request("TeslaRadarConfigRequest", request["id"])
        else:
          self.config_request = request
      elif raw_filter:
        request = self._parse_filter_request(raw_filter)
        if self._request_expired(request["id"]):
          self._publish_filter_result(request["id"], "expired", "request timestamp is invalid or expired")
          self._clear_request("TeslaRadarFilterRequest", request["id"])
        else:
          self.filter_request = request
    except (TypeError, ValueError) as exc:
      self.config_request = None
      self.filter_request = None
      if raw_config:
        self._publish_config_result("invalid", "rejected", str(exc))
        self._clear_request("TeslaRadarConfigRequest", raw_config.split(",", 1)[0])
      if raw_filter:
        self._publish_filter_result("invalid", "rejected", str(exc))
        self._clear_request("TeslaRadarFilterRequest", raw_filter.split(",", 1)[0])

  def _update_config_request(self, CC, CS, frame):
    request = self.config_request
    if request is None:
      return []
    if self._request_expired(request["id"]):
      self._publish_config_result(request["id"], "expired", "request timestamp is invalid or expired")
      self._clear_request("TeslaRadarConfigRequest", request["id"])
      self.config_request = None
      return []
    if not request["sent"]:
      if reason := self._write_block_reason(CC, CS):
        self._publish_config_result(request["id"], "waiting", reason)
        return []
      try:
        sends = [self.can.create_radar_configuration(request["field"], request["value"])]
      except ValueError as exc:
        self._publish_config_result(request["id"], "rejected", str(exc))
        self._clear_request("TeslaRadarConfigRequest", request["id"])
        self.config_request = None
        return []
      request.update(sent=True, sent_frame=frame, state_seq=self._state_seq("TeslaRadarStateSeq"))
      self._publish_config_result(request["id"], "sent", request["field"])
      return sends

    if not request["confirmed"] and self._state_seq("TeslaRadarStateSeq") > request["state_seq"] and self._config_matches(request):
      request["confirmed"] = True
      if not request["store"]:
        self._publish_config_result(request["id"], "applied", request["field"])
        self._clear_request("TeslaRadarConfigRequest", request["id"])
        self.config_request = None
        return []
    if request["confirmed"] and request["store"]:
      if reason := self._write_block_reason(CC, CS):
        self._publish_config_result(request["id"], "waiting", reason)
        return []
      self._publish_config_result(request["id"], "nvm_sent", "power-cycle verification pending")
      self._clear_request("TeslaRadarConfigRequest", request["id"])
      self.config_request = None
      return [self.can.create_radar_configuration("store_nvm", 1)]
    if frame - request["sent_frame"] > 300:
      self._publish_config_result(request["id"], "timeout", "RadarState did not confirm requested value")
      self._clear_request("TeslaRadarConfigRequest", request["id"])
      self.config_request = None
    return []

  def _update_filter_request(self, CC, CS, frame):
    request = self.filter_request
    if request is None:
      return []
    if self._request_expired(request["id"]):
      self._publish_filter_result(request["id"], "expired", "request timestamp is invalid or expired")
      self._clear_request("TeslaRadarFilterRequest", request["id"])
      self.filter_request = None
      return []
    if not request["sent"]:
      if not CS.out.canValid:
        self._publish_filter_result(request["id"], "waiting", "wait for valid CAN")
        return []
      if request["phase"] == "write" and (reason := self._write_block_reason(CC, CS)):
        self._publish_filter_result(request["id"], "waiting", reason)
        return []
      try:
        if request["phase"] == "query":
          sends = [self.can.create_filter_query(request["index"])]
        else:
          sends = [self.can.create_filter_configuration(
            request["index"], request["active"], request["minimum"], request["maximum"])]
      except ValueError as exc:
        self._publish_filter_result(request["id"], "rejected", str(exc))
        self._clear_request("TeslaRadarFilterRequest", request["id"])
        self.filter_request = None
        return []
      request.update(sent=True, sent_frame=frame, state_seq=self._state_seq("TeslaRadarFilterStateSeq"))
      status = "query_sent" if request["phase"] == "query" else "sent"
      self._publish_filter_result(request["id"], status, str(request["index"]))
      return sends

    raw_state = self._text_param("TeslaRadarFilterState")
    if raw_state and self._state_seq("TeslaRadarFilterStateSeq") > request["state_seq"]:
      try:
        state = self._parse_filter_state(raw_state)
      except ValueError:
        state = None
      if state is not None and state[0] == request["index"]:
        detail = f"{state[0]}:{int(state[1])}:{state[2]}:{state[3]}"
        if request["phase"] == "query":
          if request["query_only"]:
            self._publish_filter_result(request["id"], "queried", detail)
            self._clear_request("TeslaRadarFilterRequest", request["id"])
            self.filter_request = None
          elif self._filter_matches(request, state):
            self._publish_filter_result(request["id"], "applied", f"already:{detail}")
            self._clear_request("TeslaRadarFilterRequest", request["id"])
            self.filter_request = None
          else:
            request.update(phase="write", sent=False, sent_frame=frame)
            self._publish_filter_result(request["id"], "queried", detail)
        elif self._filter_matches(request, state):
          self._publish_filter_result(request["id"], "applied", str(request["index"]))
          self._clear_request("TeslaRadarFilterRequest", request["id"])
          self.filter_request = None
    if self.filter_request is not None and frame - request["sent_frame"] > 200:
      detail = "query" if request["phase"] == "query" else "write"
      self._publish_filter_result(request["id"], "timeout", f"FilterState did not confirm {detail}")
      self._clear_request("TeslaRadarFilterRequest", request["id"])
      self.filter_request = None
    return []

  def _runtime_configuration_sends(self, CC, CS, frame):
    self._load_next_request()
    if self.config_request is not None:
      return self._update_config_request(CC, CS, frame)
    if self.filter_request is not None:
      return self._update_filter_request(CC, CS, frame)
    return []

  def update(self, CC, CS, frame):
    self._publish_apply_state(CC, CS)
    sends = self._runtime_configuration_sends(CC, CS, frame)
    if frame % 5 == 0:
      sends.extend(self._motion_sends(CS))
    return sends
