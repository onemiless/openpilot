import logging
import math
import time

import numpy as np
from opendbc.can import CANPacker
from opendbc.car import Bus, apply_steer_angle_limits_vm, structs
from opendbc.car.interfaces import CarControllerBase
from opendbc.car.tesla.ars408_can import ARS408CAN, ARS408_FILTER_SIGNALS, ARS408_MOTION_INPUT_ENABLED
from opendbc.car.tesla.ars408_log import get_ars408_logger
from opendbc.car.tesla.coop_steering import CoopSteeringCarController
from opendbc.car.tesla.speed_sync_controller import SpeedSyncController
from opendbc.car.tesla.teslacan import TeslaCAN
from opendbc.car.tesla.turn_signal_controller import TurnSignalController
from opendbc.car.tesla.values import TESLA_SPEED_SYNC_BUILD_ENABLED, CarControllerParams, TeslaFlags
from opendbc.car.vehicle_model import VehicleModel
from openpilot.common.params import Params

log = logging.getLogger(__name__)
radar_log = get_ars408_logger("card")
ARS408_REQUEST_TTL_MS = 30 * 60 * 1000


class CarController(CarControllerBase):
  def __init__(self, dbc_names, CP):
    super().__init__(dbc_names, CP)
    self.apply_angle_last = 0.0
    # Keep the planner-limited base separate from the final cooperative output.
    # Feeding the driver offset back into the base accumulates a permanent angle.
    self.planner_apply_angle_last = 0.0
    self.packer = CANPacker(dbc_names[Bus.party])
    self.tesla_can = TeslaCAN(self.packer)
    self.ars408_can = None if CP.radarUnavailable else ARS408CAN()
    self.params = Params()
    self.VM = VehicleModel(CP)
    self.coop_steering = CoopSteeringCarController()
    self.coop_steering_enabled = self.params.get_bool("TeslaCoopSteering")
    self.radar_motion_enabled = self.params.get_bool("TeslaRadarMotionInput")
    self._radar_motion_valid_prev = None
    self._coop_override_prev = False
    self._coop_saturated_prev = False
    self._steering_disengage_prev = False
    self._steering_override_prev = False
    self._radar_config_request = None
    self._radar_filter_request = None
    self.turn_signal_controller = TurnSignalController(
      bool(CP.flags & TeslaFlags.TURN_SIGNAL_TEST),
      auto_configured=bool(CP.flags & TeslaFlags.AUTO_TURN_SIGNAL),
    )
    # Fail closed even if stale CarParams still contain SPEED_SYNC after an update.
    self.speed_sync_controller = SpeedSyncController(
      TESLA_SPEED_SYNC_BUILD_ENABLED and bool(CP.flags & TeslaFlags.SPEED_SYNC),
    )
    self.speed_sync_target_mps = 0.0
    self.speed_sync_target_valid = False
    log.info("Tesla cooperative steering configured enabled=%d", int(self.coop_steering_enabled))
    radar_log.info("ARS408 motion input configured enabled=%d bus=1 rate_hz=20", int(self.radar_motion_enabled))

  def observe_aux_can(self, monotonic_nanos, address, data, source):
    self.turn_signal_controller.observe(monotonic_nanos, address, data, source)
    self.speed_sync_controller.observe(monotonic_nanos, address, data, source)

  def set_speed_sync_target(self, speed_mps, valid):
    self.speed_sync_target_mps = float(speed_mps) if valid else 0.0
    self.speed_sync_target_valid = bool(valid)

  def update_turn_signal_context(self, now_nanos, **context):
    self.turn_signal_controller.update_lane_change_context(now_nanos, **context)

  def take_turn_signal_cancel_sends(self, now_nanos):
    return self.turn_signal_controller.take_can_sends(now_nanos, cancel_only=True)

  def send_radar_motion(self, CS):
    """Return reviewed ARS408 motion frames when the physical CAN path is safe."""
    if self.ars408_can is None or not ARS408_MOTION_INPUT_ENABLED:
      return []

    enabled = self.params.get_bool("TeslaRadarMotionInput")
    if enabled != self.radar_motion_enabled:
      radar_log.info("ARS408 motion input runtime enabled=%d", int(enabled))
      self.radar_motion_enabled = enabled
      self._radar_motion_valid_prev = None
    if not enabled:
      return []

    speed_mps = float(CS.out.vEgoRaw)
    yaw_rate_rad_s = float(CS.out.yawRate)
    motion_valid = bool(CS.out.canValid) and math.isfinite(speed_mps) and math.isfinite(yaw_rate_rad_s)
    if motion_valid != self._radar_motion_valid_prev:
      radar_log.info("ARS408 motion source valid=%d speed=%.3f yaw_rate_rad_s=%.4f",
                     int(motion_valid), speed_mps, yaw_rate_rad_s)
      self._radar_motion_valid_prev = motion_valid
    if not motion_valid:
      return []

    reverse = CS.out.gearShifter == structs.CarState.GearShifter.reverse
    standstill = CS.out.standstill or abs(speed_mps) < 0.05
    direction = 0 if standstill else (2 if reverse else 1)
    yaw_rate_deg_s = math.degrees(-yaw_rate_rad_s if reverse else yaw_rate_rad_s)
    return [
      self.ars408_can.create_speed_information(speed_mps, direction),
      self.ars408_can.create_yaw_rate_information(yaw_rate_deg_s),
    ]

  @staticmethod
  def _parse_radar_config_request(raw):
    request_id, field, value, store = raw.split(",", 3)
    if field not in ("max_distance", "send_extended", "output_type"):
      raise ValueError(f"unsupported field {field}")
    value, store = int(value), int(store)
    if store not in (0, 1):
      raise ValueError("store must be 0 or 1")
    return {"id": request_id, "field": field, "value": value, "store": bool(store),
            "sent": False, "confirmed": False, "sent_frame": 0, "state_seq": 0}

  @staticmethod
  def _parse_radar_filter_request(raw):
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
    return (int(time.time() * 1000) if now_ms is None else now_ms) - created_ms > ARS408_REQUEST_TTL_MS

  def _pop_radar_request(self, key):
    raw = self.params.get(key, encoding="utf8")
    if not raw:
      return None
    requests = [line.strip() for line in raw.splitlines() if line.strip()]
    if len(requests) <= 1:
      self.params.remove(key)
    else:
      self.params.put_nonblocking(key, "\n".join(requests[1:]))
    return requests[0]

  def _state_seq(self, key):
    raw = self.params.get(key)
    try:
      return int(raw) if raw is not None else 0
    except (TypeError, ValueError):
      return 0

  @staticmethod
  def _configuration_ready(CS):
    return bool(CS.out.canValid)

  def _publish_config_result(self, request_id, status, detail=""):
    self.params.put_nonblocking("TeslaRadarConfigResult", f"{request_id},{status},{detail}")

  def _publish_filter_result(self, request_id, status, detail=""):
    self.params.put_nonblocking("TeslaRadarFilterResult", f"{request_id},{status},{detail}")

  def _radar_config_matches(self, request):
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
  def _filter_state_matches(request, state):
    index, active, minimum, maximum = state
    resolution = ARS408_FILTER_SIGNALS[request["index"]][3]
    return index == request["index"] and active == request["active"] and \
      math.isclose(minimum, request["minimum"], abs_tol=resolution / 2 + 1e-6) and \
      math.isclose(maximum, request["maximum"], abs_tol=resolution / 2 + 1e-6)

  def update_radar_configuration(self, CC, CS):
    """Process one field-scoped RadarCfg or one atomic Object FilterCfg request."""
    sends = []
    if self.ars408_can is None:
      return sends

    if self._radar_config_request is None and self._radar_filter_request is None:
      raw_config = self._pop_radar_request("TeslaRadarConfigRequest")
      raw_filter = None if raw_config else self._pop_radar_request("TeslaRadarFilterRequest")
      try:
        if raw_config:
          self._radar_config_request = self._parse_radar_config_request(raw_config)
          if self._request_expired(self._radar_config_request["id"]):
            self._publish_config_result(self._radar_config_request["id"], "expired", "request older than 30 minutes")
            self._radar_config_request = None
        elif raw_filter:
          self._radar_filter_request = self._parse_radar_filter_request(raw_filter)
          if self._request_expired(self._radar_filter_request["id"]):
            self._publish_filter_result(self._radar_filter_request["id"], "expired", "request older than 30 minutes")
            self._radar_filter_request = None
      except (TypeError, ValueError) as exc:
        if raw_config:
          self._publish_config_result("invalid", "rejected", str(exc))
        if raw_filter:
          self._publish_filter_result("invalid", "rejected", str(exc))

    request = self._radar_config_request
    if request is not None:
      if self._request_expired(request["id"]):
        self._publish_config_result(request["id"], "expired", "request older than 30 minutes")
        self._radar_config_request = None
        return sends
      if not request["sent"]:
        if not self._configuration_ready(CS):
          self._publish_config_result(request["id"], "waiting", "wait for valid CAN")
          return sends
        try:
          sends.append(self.ars408_can.create_radar_configuration(request["field"], request["value"]))
        except ValueError as exc:
          self._publish_config_result(request["id"], "rejected", str(exc))
          self._radar_config_request = None
          return sends
        request["sent"] = True
        request["sent_frame"] = self.frame
        request["state_seq"] = self._state_seq("TeslaRadarStateSeq")
        self._publish_config_result(request["id"], "sent", request["field"])
      elif not request["confirmed"] and self._state_seq("TeslaRadarStateSeq") > request["state_seq"] and \
           self._radar_config_matches(request):
        request["confirmed"] = True
        if not request["store"]:
          self._publish_config_result(request["id"], "applied", request["field"])
          self._radar_config_request = None
      if request is self._radar_config_request and request["confirmed"] and request["store"]:
        if not self._configuration_ready(CS):
          self._publish_config_result(request["id"], "waiting", "wait for valid CAN before NVM write")
        else:
          sends.append(self.ars408_can.create_radar_configuration("store_nvm", 1))
          self._publish_config_result(request["id"], "nvm_sent", "power-cycle verification pending")
          self._radar_config_request = None
      elif request is self._radar_config_request and not request["confirmed"] and self.frame - request["sent_frame"] > 300:
        self._publish_config_result(request["id"], "timeout", "RadarState did not confirm requested value")
        self._radar_config_request = None
      return sends

    request = self._radar_filter_request
    if request is not None:
      if self._request_expired(request["id"]):
        self._publish_filter_result(request["id"], "expired", "request older than 30 minutes")
        self._radar_filter_request = None
        return sends
      if not request["sent"]:
        if not self._configuration_ready(CS):
          self._publish_filter_result(request["id"], "waiting", "wait for valid CAN")
          return sends
        try:
          if request["phase"] == "query":
            sends.append(self.ars408_can.create_filter_query(request["index"]))
          else:
            sends.append(self.ars408_can.create_filter_configuration(
              request["index"], request["active"], request["minimum"], request["maximum"]))
        except ValueError as exc:
          self._publish_filter_result(request["id"], "rejected", str(exc))
          self._radar_filter_request = None
          return sends
        request["sent"] = True
        request["sent_frame"] = self.frame
        request["state_seq"] = self._state_seq("TeslaRadarFilterStateSeq")
        status = "query_sent" if request["phase"] == "query" else "sent"
        self._publish_filter_result(request["id"], status, str(request["index"]))
      else:
        raw_state = self.params.get("TeslaRadarFilterState", encoding="utf8")
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
                self._radar_filter_request = None
              elif self._filter_state_matches(request, state):
                self._publish_filter_result(request["id"], "applied", f"already:{detail}")
                self._radar_filter_request = None
              else:
                request["phase"] = "write"
                request["sent"] = False
                request["sent_frame"] = self.frame
                self._publish_filter_result(request["id"], "queried", detail)
            elif self._filter_state_matches(request, state):
              self._publish_filter_result(request["id"], "applied", str(request["index"]))
              self._radar_filter_request = None
        if self._radar_filter_request is not None and self.frame - request["sent_frame"] > 200:
          detail = "query" if request["phase"] == "query" else "write"
          self._publish_filter_result(request["id"], "timeout", f"FilterState did not confirm {detail}")
          self._radar_filter_request = None
    return sends

  def update_steering_control(self, desired_angle, lat_active, CS):
    self.planner_apply_angle_last = apply_steer_angle_limits_vm(
      desired_angle, self.planner_apply_angle_last, CS.out.vEgoRaw,
      CS.out.steeringAngleDeg, lat_active, CarControllerParams, self.VM,
    )

    coop_steering = self.coop_steering.update(
      self.planner_apply_angle_last, lat_active, self.coop_steering_enabled, CS, self.VM,
    )
    self.apply_angle_last = coop_steering.steeringAngleDeg
    return self.apply_angle_last, coop_steering.lat_active

  def update(self, CC, CS, now_nanos):
    actuators = CC.actuators
    can_sends = []

    can_sends.extend(self.update_radar_configuration(CC, CS))

    # Bus 1 is gateway-managed; ARS408 frames remain constrained by Panda safety.
    if self.frame % 5 == 0:
      can_sends.extend(self.send_radar_motion(CS))

    # Disengage and allow for user override on high torque inputs
    # TODO: move this to a generic disengageRequested carState field and set CC.cruiseControl.cancel based on it
    steering_disengage = CS.out.steeringDisengage
    steering_override = CS.out.steeringOverride
    cruise_cancel = CC.cruiseControl.cancel or steering_disengage
    # CarState faults are checked again here so a newly received EPS inhibit
    # cannot leak one stale active request through the asynchronous control path.
    lat_active = (CC.latActive and not steering_disengage and not steering_override and
                  not CS.out.steerFaultTemporary and not CS.out.steerFaultPermanent)
    if steering_disengage != self._steering_disengage_prev:
      log.warning("Tesla steering safety disengage=%d torque=%.2f hands_on_level=%d eac_status=%s eac_error_code=%d",
                  int(steering_disengage), CS.out.steeringTorque, CS.hands_on_level,
                  CS.eac_status, CS.eac_error_code)
      self._steering_disengage_prev = steering_disengage
    if steering_override != self._steering_override_prev:
      log.warning("Tesla cooperative steering pause=%d torque=%.2f hands_on_level=%d steering_rate=%.2f",
                  int(steering_override), CS.out.steeringTorque, CS.hands_on_level, CS.out.steeringRateDeg)
      self._steering_override_prev = steering_override

    if self.frame % 2 == 0:
      self.apply_angle_last, lat_active = self.update_steering_control(actuators.steeringAngleDeg, lat_active, CS)

      if self.coop_steering.driver_override_active != self._coop_override_prev:
        log.info("Tesla cooperative steering driver_override=%d torque=%.2f planner_angle=%.2f override_angle=%.2f output_angle=%.2f",
                 int(self.coop_steering.driver_override_active), CS.out.steeringTorque,
                 self.planner_apply_angle_last, self.coop_steering.angle_override, self.apply_angle_last)
        self._coop_override_prev = self.coop_steering.driver_override_active
      if self.coop_steering.angle_saturated != self._coop_saturated_prev:
        log.info("Tesla cooperative steering saturated=%d torque=%.2f planner_angle=%.2f override_angle=%.2f output_angle=%.2f",
                 int(self.coop_steering.angle_saturated), CS.out.steeringTorque,
                 self.planner_apply_angle_last, self.coop_steering.angle_override, self.apply_angle_last)
        self._coop_saturated_prev = self.coop_steering.angle_saturated

      can_sends.append(self.tesla_can.create_steering_control(self.apply_angle_last, lat_active, (self.frame // 2) % 16))

    if self.frame % 10 == 0:
      can_sends.append(self.tesla_can.create_steering_allowed((self.frame // 10) % 16))

    # Longitudinal control
    if self.CP.openpilotLongitudinalControl:
      if self.frame % 4 == 0:
        state = 13 if cruise_cancel else 4  # 4=ACC_ON, 13=ACC_CANCEL_GENERIC_SILENT
        accel = float(np.clip(actuators.accel, CarControllerParams.ACCEL_MIN, CarControllerParams.ACCEL_MAX))
        cntr = (self.frame // 4) % 8
        can_sends.append(self.tesla_can.create_longitudinal_command(state, accel, cntr, CS.out.vEgo, CC.longActive))

    else:
      # Increment counter so cancel is prioritized even without openpilot longitudinal
      if cruise_cancel:
        cntr = (CS.das_control["DAS_controlCounter"] + 1) % 8
        can_sends.append(self.tesla_can.create_longitudinal_command(13, 0, cntr, CS.out.vEgo, False))

    can_sends.extend(self.speed_sync_controller.update(
      CC, CS, self.speed_sync_target_mps, self.speed_sync_target_valid, now_nanos,
    ))
    can_sends.extend(self.turn_signal_controller.take_can_sends(now_nanos))

    # TODO: HUD control
    new_actuators = actuators.as_builder()
    new_actuators.steeringAngleDeg = self.apply_angle_last

    self.frame += 1
    return new_actuators, can_sends
