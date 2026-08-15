import logging
import math
import time
from collections import deque
from enum import IntEnum

import numpy as np
from opendbc.can import CANPacker
from opendbc.car import Bus, apply_steer_angle_limits_vm, structs
from opendbc.car.interfaces import CarControllerBase
from opendbc.car.tesla.ars408_can import ARS408CAN, ARS408_FILTER_SIGNALS, ARS408_MOTION_INPUT_ENABLED
from opendbc.car.tesla.ars408_log import get_ars408_logger
from opendbc.car.tesla.coop_steering import CoopSteeringCarController
from opendbc.car.tesla.cruise_diagnostics import classify_cruise_snapshot, decode_das_control_payload, is_cruise_failure_transition
from opendbc.car.tesla.speed_sync_controller import SpeedSyncController
from opendbc.car.tesla.teslacan import TeslaCAN
from opendbc.car.tesla.turn_signal_controller import TurnSignalController
from opendbc.car.tesla.values import CarControllerParams, TeslaFlags
from opendbc.car.vehicle_model import VehicleModel
from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog

log = logging.getLogger(__name__)
radar_log = get_ars408_logger("card")
ARS408_REQUEST_TTL_MS = 30 * 60 * 1000
TESLA_LONGITUDINAL_OEM_FRESHNESS_NS = 200_000_000
TESLA_LONGITUDINAL_HANDOFF_SETTLE_NS = 400_000_000
TESLA_LONGITUDINAL_ADDRESS = 0x2B9
TESLA_LONGITUDINAL_TX_INTERVAL_WARN_NS = 55_000_000
PANDA_TX_ECHO_BASE = 0x80
PANDA_TX_REJECTED_BASE = 0xC0


class LongitudinalAction(IntEnum):
  NONE = 0
  CONTROL = 1
  CANCEL = 2
  RELEASE = 3


class TeslaLongitudinalOwnership:
  """Sequence CP control, one cancel frame, then an internal OEM handoff marker."""

  def __init__(self):
    self.cp_active = False
    self.release_pending = False

  def update(self, long_active: bool, cancel: bool) -> LongitudinalAction:
    if self.release_pending:
      self.release_pending = False
      return LongitudinalAction.RELEASE
    if self.cp_active and (cancel or not long_active):
      self.cp_active = False
      self.release_pending = True
      return LongitudinalAction.CANCEL
    if long_active and not cancel:
      self.cp_active = True
      return LongitudinalAction.CONTROL
    return LongitudinalAction.NONE


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
    self.speed_sync_controller = SpeedSyncController(bool(CP.flags & TeslaFlags.SPEED_SYNC))
    self.speed_sync_target_mps = 0.0
    self.speed_sync_target_valid = False
    self.longitudinal_ownership = TeslaLongitudinalOwnership()
    self.longitudinal_counter = None
    self.longitudinal_handoff_nanos = 0
    self.last_long_control_frame = -4
    self._cruise_state_prev = None
    self._cruise_diag_history = deque(maxlen=50)
    self._last_long_tx = {}
    self._last_vehicle_long_tx_nanos = 0
    self._last_cp_tx_counter = None
    self._last_long_tx_echo_nanos = 0
    self._last_long_tx_echo = {}
    log.info("Tesla cooperative steering configured enabled=%d", int(self.coop_steering_enabled))
    radar_log.info("ARS408 motion input configured enabled=%d bus=1 rate_hz=20", int(self.radar_motion_enabled))

  def observe_aux_can(self, monotonic_nanos, address, data, source):
    self.turn_signal_controller.observe(monotonic_nanos, address, data, source)
    self.speed_sync_controller.observe(monotonic_nanos, address, data, source)
    self._observe_longitudinal_tx_echo(monotonic_nanos, address, data, source)

  def _observe_longitudinal_tx_echo(self, monotonic_nanos, address, data, source):
    if address != TESLA_LONGITUDINAL_ADDRESS or source < PANDA_TX_ECHO_BASE:
      return

    rejected = source >= PANDA_TX_REJECTED_BASE
    returned_bus = source - (PANDA_TX_REJECTED_BASE if rejected else PANDA_TX_ECHO_BASE)
    payload = decode_das_control_payload(bytes(data))
    echo = {
      "echo_kind": "rejected" if rejected else "tx_echo",
      "echo_nanos": int(monotonic_nanos),
      "echo_bus": int(returned_bus),
      **payload,
    }
    echo["echo_matches_last_attempt"] = payload["tx_raw"] == self._last_long_tx.get("tx_raw")

    if not rejected:
      previous_echo_nanos = self._last_long_tx_echo_nanos
      echo["echo_interval_ms"] = None
      if previous_echo_nanos and monotonic_nanos >= previous_echo_nanos:
        echo["echo_interval_ms"] = round((monotonic_nanos - previous_echo_nanos) / 1e6, 3)
      self._last_long_tx_echo_nanos = int(monotonic_nanos)

    self._last_long_tx_echo = echo
    if rejected or (echo.get("echo_interval_ms") is not None and
                    echo["echo_interval_ms"] > TESLA_LONGITUDINAL_TX_INTERVAL_WARN_NS / 1e6):
      cloudlog.event("tesla.das_control_returned", error=rejected, **echo)

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

  def update_longitudinal_control(self, CC, CS, cruise_cancel, now_nanos):
    if not self.CP.openpilotLongitudinalControl:
      if not cruise_cancel:
        return []
      cntr = (CS.das_control["DAS_controlCounter"] + 1) % 8
      command = self.tesla_can.create_longitudinal_command(13, 0, cntr, CS.out.vEgo, False)
      self._record_longitudinal_tx("cancel", command, now_nanos)
      return [command]

    if self.frame - self.last_long_control_frame < 4:
      return []

    if self.longitudinal_handoff_nanos:
      if now_nanos < self.longitudinal_handoff_nanos or \
         now_nanos - self.longitudinal_handoff_nanos < TESLA_LONGITUDINAL_HANDOFF_SETTLE_NS:
        return []
      self.longitudinal_handoff_nanos = 0

    das_control_nanos = int(getattr(CS, "das_control_nanos", 0))
    oem_state_fresh = (das_control_nanos > 0 and now_nanos >= das_control_nanos and
                       now_nanos - das_control_nanos <= TESLA_LONGITUDINAL_OEM_FRESHNESS_NS)
    # Fresh OEM data is required to acquire the stream. Once CP owns it, a
    # short parser gap must not cause an uncommanded source switch.
    long_active = (CC.longActive and not CS.out.brakePressed and
                   (self.longitudinal_ownership.cp_active or oem_state_fresh))
    action = self.longitudinal_ownership.update(long_active, cruise_cancel)

    if action == LongitudinalAction.CONTROL:
      if self.longitudinal_counter is None:
        self.longitudinal_counter = int(CS.das_control["DAS_controlCounter"])
        self.tesla_can.reset_longitudinal_jerk()
      self.longitudinal_counter = (self.longitudinal_counter + 1) % 8
      accel = float(np.clip(CC.actuators.accel, CarControllerParams.ACCEL_MIN, CarControllerParams.ACCEL_MAX))
      command = self.tesla_can.create_longitudinal_command(4, accel, self.longitudinal_counter, CS.out.vEgo, True)
      self._record_longitudinal_tx("control", command, now_nanos)
      self.last_long_control_frame = self.frame
      return [command]

    if action == LongitudinalAction.CANCEL:
      self.longitudinal_counter = (self.longitudinal_counter + 1) % 8
      self.tesla_can.reset_longitudinal_jerk()
      command = self.tesla_can.create_longitudinal_command(13, 0, self.longitudinal_counter, CS.out.vEgo, False)
      self._record_longitudinal_tx("cancel", command, now_nanos)
      self.last_long_control_frame = self.frame
      return [command]

    if action == LongitudinalAction.RELEASE:
      handoff_counter = self.longitudinal_counter
      self.longitudinal_counter = None
      self.longitudinal_handoff_nanos = now_nanos
      command = self.tesla_can.create_stock_longitudinal_handoff(CS.das_control, handoff_counter)
      self._record_longitudinal_tx("handoff_marker", command, now_nanos)
      self._last_cp_tx_counter = None
      self._last_vehicle_long_tx_nanos = 0
      return [command]

    return []

  def _record_longitudinal_tx(self, kind, command, now_nanos):
    payload = decode_das_control_payload(bytes(command[1]))
    vehicle_candidate = payload["tx_aeb_event"] == 0
    previous_tx_nanos = getattr(self, "_last_vehicle_long_tx_nanos", 0)
    tx_interval_ms = None
    if vehicle_candidate:
      if previous_tx_nanos and now_nanos >= previous_tx_nanos:
        tx_interval_ms = round((now_nanos - previous_tx_nanos) / 1e6, 3)
      self._last_vehicle_long_tx_nanos = now_nanos

    counter_gap = False
    if vehicle_candidate:
      previous_counter = getattr(self, "_last_cp_tx_counter", None)
      if previous_counter is not None:
        counter_gap = payload["tx_counter"] != (previous_counter + 1) % 8
      self._last_cp_tx_counter = payload["tx_counter"]

    self._last_long_tx = {
      "tx_kind": kind,
      "tx_interval_ms": tx_interval_ms,
      "tx_counter_gap": counter_gap,
      "tx_attempted_nanos": now_nanos,
      **payload,
    }

  def _cruise_diagnostic_snapshot(self, CC, CS, now_nanos):
    snapshot = dict(getattr(CS, "cruise_diagnostics", {}))
    snapshot.update({
      "frame": self.frame,
      "now_nanos": now_nanos,
      "cruise_state": getattr(CS, "cruise_state", None),
      "cc_enabled": bool(CC.enabled),
      "cc_long_active": bool(CC.longActive),
      "cc_lat_active": bool(CC.latActive),
      "cc_cancel": bool(CC.cruiseControl.cancel),
      "cp_2b9_active": bool(self.longitudinal_ownership.cp_active),
      "cp_2b9_release_pending": bool(self.longitudinal_ownership.release_pending),
    })
    snapshot.update(self._last_long_tx)
    snapshot.update({f"physical_{key}": value for key, value in self._last_long_tx_echo.items()})
    if self._last_long_tx:
      snapshot["tx_attempt_age_ms"] = round((now_nanos - self._last_long_tx["tx_attempted_nanos"]) / 1e6, 1)
    physical_echo_nanos = self._last_long_tx_echo.get("echo_nanos")
    if physical_echo_nanos is not None:
      snapshot["physical_echo_age_ms"] = round((now_nanos - physical_echo_nanos) / 1e6, 1)
    return snapshot

  def log_cruise_diagnostic(self, CC, CS, now_nanos):
    snapshot = self._cruise_diagnostic_snapshot(CC, CS, now_nanos)
    current = snapshot["cruise_state"]
    previous = getattr(self, "_cruise_state_prev", None)
    transition = current != previous
    if self.frame % 4 == 0 or transition:
      self._cruise_diag_history.append(snapshot)
    if is_cruise_failure_transition(previous, current):
      classification = classify_cruise_snapshot(snapshot)
      cloudlog.event("tesla.cruise_fault_diagnostic", error=True,
                     previous_state=previous, current_state=current,
                     classification=classification, history=list(self._cruise_diag_history))
      log.error("Tesla cruise fault %s->%s classification=%s tx=%s",
                previous, current, classification, self._last_long_tx)
    self._cruise_state_prev = current

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

    can_sends.extend(self.update_longitudinal_control(CC, CS, cruise_cancel, now_nanos))
    self.log_cruise_diagnostic(CC, CS, now_nanos)

    can_sends.extend(self.speed_sync_controller.update(
      CC, CS, self.speed_sync_target_mps, self.speed_sync_target_valid, now_nanos,
    ))
    can_sends.extend(self.turn_signal_controller.take_can_sends(now_nanos))

    # TODO: HUD control
    new_actuators = actuators.as_builder()
    new_actuators.steeringAngleDeg = self.apply_angle_last

    self.frame += 1
    return new_actuators, can_sends
