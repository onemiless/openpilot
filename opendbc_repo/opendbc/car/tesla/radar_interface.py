import logging
import math

from opendbc.can import CANParser
from opendbc.car import structs
from opendbc.car.interfaces import RadarInterfaceBase
from opendbc.car.tesla.ars408_can import (
  ARS408_BUS, ARS408_MAX_DISTANCE, ARS408_SEND_EXTENDED, ARS408_SENSOR_ID,
)
from openpilot.common.params import Params


ARS408_DBC = "ARS408"
ARS408_ADDRESS_OFFSET = ARS408_SENSOR_ID << 4

# The DBC describes SensorID 0. The radar is configured as SensorID 5 so that
# its CAN namespace does not collide with Tesla bus 1 traffic. Incoming frames
# are validated at their shifted addresses, then mapped back for DBC decoding.
ARS408_STATUS = 0x60A + ARS408_ADDRESS_OFFSET
ARS408_GENERAL = 0x60B + ARS408_ADDRESS_OFFSET
ARS408_QUALITY = 0x60C + ARS408_ADDRESS_OFFSET
ARS408_EXTENDED = 0x60D + ARS408_ADDRESS_OFFSET
ARS408_RADAR_STATE = 0x201 + ARS408_ADDRESS_OFFSET
ARS408_MESSAGES = {
  ARS408_STATUS: (0x60A, "Obj_0_Status", 4),
  ARS408_GENERAL: (0x60B, "Obj_1_General", 8),
  ARS408_QUALITY: (0x60C, "Obj_2_Quality", 7),
  ARS408_EXTENDED: (0x60D, "Obj_3_Extended", 8),
}
ARS408_PROTOCOL_MAX_OBJECTS = 100
ARS408_OBJECT_CORRIDOR = 5.5
ARS408_MIN_PROBABILITY = 3       # >= 75%
ARS408_MIN_TRACKED_PROBABILITY = 2  # >= 50%, Toyota-style hysteresis for an existing track
ARS408_MIN_STATIC_PROBABILITY = 5  # >= 99%
ARS408_TRACK_GRACE_CYCLES = 2
LOG_EVERY_CYCLES = 20
# RadarState is nominally 1 Hz. Cover the ten-second startup configuration
# window before turning a transient default configuration into a fault.
CONFIG_GRACE_STATE_FRAMES = 10
ARS408_STARTUP_GRACE_UPDATES = 1000
ARS408_STATUS_TIMEOUT_UPDATES = 50
ARS408_STATE_TIMEOUT_UPDATES = 300
ARS408_ERROR_PUBLISH_INTERVAL = 5
ARS408_INTERFERENCE_CONFIRM_FRAMES = 2

log = logging.getLogger(__name__)


def object_rejection_reason(obj, previously_tracked=False, timed_out=False):
  if timed_out:
    return "timeout"

  measurement_state = int(obj["Obj_MeasState"])
  probability = int(obj["Obj_ProbOfExist"])
  d_rel = float(obj["Obj_DistLong"])
  y_rel = -float(obj["Obj_DistLat"])
  v_rel = float(obj["Obj_VrelLong"])
  yv_rel = float(obj["Obj_VrelLat"])
  dynamic_property = int(obj["Obj_DynProp"])

  min_probability = ARS408_MIN_TRACKED_PROBABILITY if previously_tracked else ARS408_MIN_PROBABILITY
  if measurement_state in (0, 4):
    return "invalid"
  if probability < min_probability:
    return "low probability"
  # A predicted-only target must first have been observed by the interface.
  if measurement_state == 3 and not previously_tracked:
    return "invalid"
  if not (0.0 <= d_rel <= ARS408_MAX_DISTANCE and abs(y_rel) <= 100.0 and
          -100.0 <= v_rel <= 100.0 and abs(yv_rel) <= 60.0):
    return "out of range"

  # ARS408 reports roadside infrastructure as stationary/candidate/crossing
  # stationary. Keep stopped targets (7), and only keep never-moving static
  # targets when they are high-confidence and within the current/adjacent
  # three-lane corridor.
  if dynamic_property in (1, 3, 5):
    if probability < ARS408_MIN_STATIC_PROBABILITY:
      return "low probability"
    if abs(y_rel) > ARS408_OBJECT_CORRIDOR:
      return "out of range"
  return None


def object_is_usable(obj, previously_tracked=False):
  return object_rejection_reason(obj, previously_tracked) is None


def get_radar_can_parser(CP):
  messages = [
    ("Obj_0_Status", 14),
    ("Obj_1_General", math.nan),
    ("Obj_2_Quality", math.nan),
    ("Obj_3_Extended", math.nan),
    ("RadarState", math.nan),
  ]
  return CANParser(ARS408_DBC, messages, ARS408_BUS)


class RadarInterface(RadarInterfaceBase):
  def __init__(self, CP):
    super().__init__(CP)
    self.params = Params()
    mode = self.params.get_int("TeslaRadarMode")
    self.radar_mode = mode if mode in (1, 2, 3) else 0
    self.rcp = None if CP.radarUnavailable else get_radar_can_parser(CP)
    self.trigger_msg = ARS408_STATUS
    self.cycle_started = False
    self.expected_objects = 0
    self.cycle_frames = []
    self.part_ids = {address: set() for address in (ARS408_GENERAL, ARS408_QUALITY, ARS408_EXTENDED)}
    self.part_counts = {address: 0 for address in self.part_ids}
    self.cycle_invalid = False
    self.incomplete_cycles = 0
    self.last_logged_incomplete = 0
    self.last_radar_state = None
    self.last_fault_signature = None
    self.radar_state_frames = 0
    self.track_miss_counts = {}
    self.update_count = 0
    self.last_status_update = None
    self.last_radar_state_update = None
    self.last_missing_can_signature = None
    self.last_rejection_reasons = {}
    self.interference_frames = 0

  def _set_status(self, ret):
    ret.radarOnline = getattr(self, "last_status_update", None) is not None and self._missing_can_signature() is None
    ret.canValid = bool(self.rcp.can_valid) and self._missing_can_signature() is None
    ret.objectCount = max(0, min(self.expected_objects, ARS408_PROTOCOL_MAX_OBJECTS))
    ret.mode = getattr(self, "radar_mode", 0)

  def _missing_can_signature(self):
    update_count = getattr(self, "update_count", 0)
    if update_count <= ARS408_STARTUP_GRACE_UPDATES:
      return None

    last_status_update = getattr(self, "last_status_update", None)
    last_radar_state_update = getattr(self, "last_radar_state_update", None)
    status_missing = last_status_update is None or \
                     update_count - last_status_update > ARS408_STATUS_TIMEOUT_UPDATES
    state_missing = last_radar_state_update is None or \
                    update_count - last_radar_state_update > ARS408_STATE_TIMEOUT_UPDATES
    return (status_missing, state_missing) if status_missing or state_missing else None

  def _apply_missing_can_error(self, ret):
    missing_signature = self._missing_can_signature()
    last_signature = getattr(self, "last_missing_can_signature", None)
    if missing_signature != last_signature:
      if missing_signature is None:
        if last_signature is not None:
          log.info("ARS408 required CAN messages recovered")
      else:
        log.error("ARS408 required CAN messages missing: object_status=%d radar_state=%d update=%d",
                  int(missing_signature[0]), int(missing_signature[1]), self.update_count)
      self.last_missing_can_signature = missing_signature

    if missing_signature is not None:
      ret.errors.canError = True
    self._set_status(ret)
    return missing_signature is not None

  def _start_cycle(self):
    status = self.rcp.vl["Obj_0_Status"]
    self.expected_objects = int(status["Obj_NofObjects"])
    self.cycle_frames = []
    self.part_ids = {address: set() for address in (ARS408_GENERAL, ARS408_QUALITY, ARS408_EXTENDED)}
    self.part_counts = {address: 0 for address in self.part_ids}
    self.cycle_invalid = self.expected_objects > ARS408_PROTOCOL_MAX_OBJECTS or int(status["Obj_InterfaceVersion"]) != 1
    self.cycle_started = True

  def _add_detail_frame(self, address, frame, object_id):
    self.cycle_frames.append(frame)
    self.part_counts[address] += 1
    self.part_ids[address].add(object_id)

  def _cycle_complete(self):
    if self.cycle_invalid:
      return False

    expected = self.expected_objects
    general_ids = self.part_ids[ARS408_GENERAL]
    quality_ids = self.part_ids[ARS408_QUALITY]
    return len(general_ids) == expected and \
           len(quality_ids) == expected and \
           self.part_counts[ARS408_GENERAL] == expected and \
           self.part_counts[ARS408_QUALITY] == expected and \
           general_ids == quality_ids

  def _extended_complete(self):
    expected = self.expected_objects
    extended_ids = self.part_ids[ARS408_EXTENDED]
    return len(extended_ids) == expected and \
           self.part_counts[ARS408_EXTENDED] == expected and \
           extended_ids == self.part_ids[ARS408_GENERAL]

  def _incomplete_result(self):
    self.incomplete_cycles += 1
    if self.incomplete_cycles == 1 or self.incomplete_cycles - self.last_logged_incomplete >= LOG_EVERY_CYCLES:
      general_ids = self.part_ids[ARS408_GENERAL]
      quality_ids = self.part_ids[ARS408_QUALITY]
      log.warning("ARS408 incomplete cycle: expected=%d general=%d quality=%d missing_general=%s missing_quality=%s consecutive=%d",
                  self.expected_objects, self.part_counts[ARS408_GENERAL], self.part_counts[ARS408_QUALITY],
                  sorted(quality_ids - general_ids), sorted(general_ids - quality_ids), self.incomplete_cycles)
      self.last_logged_incomplete = self.incomplete_cycles

    # A dropped object-list frame is not proof of a broken CAN connection.
    # Publish the last complete set so radard remains alive and diagnoses do
    # not become the generic "check connections" alert.
    ret = structs.RadarData()
    ret.points = [] if self.radar_mode == 1 else list(self.pts.values())
    if not self.rcp.can_valid:
      ret.errors.canError = True
    self._apply_radar_state_errors(ret)
    self._apply_missing_can_error(ret)
    return ret

  def _update_radar_state(self, timestamp, data, src):
    self.rcp.update([(timestamp, [(0x201, data, src)])])
    self.last_radar_state_update = self.update_count
    state = self.rcp.vl["RadarState"]
    self.last_radar_state = dict(state)
    self.radar_state_frames += 1

  def _apply_radar_state_errors(self, ret):
    state = self.last_radar_state
    if state is None:
      return

    interference = bool(int(state["RadarState_Interference"]))
    self.interference_frames = getattr(self, "interference_frames", 0) + 1 if interference else 0
    interference_fault = self.interference_frames >= ARS408_INTERFERENCE_CONFIRM_FRAMES
    temporary_fault = interference_fault or any(int(state[name]) for name in (
      "RadarState_Temperature_Error", "RadarState_Temporary_Error"))
    hard_fault = any(int(state[name]) for name in (
      "RadarState_Voltage_Error", "RadarState_Persistent_Error"))
    config_expectations = (
      ("sensor_id", "RadarState_SensorID", ARS408_SENSOR_ID),
      ("output_type", "RadarState_OutputTypeCfg", 1),
      ("quality", "RadarState_SendQualityCfg", 1),
      ("extended", "RadarState_SendExtInfoCfg", int(ARS408_SEND_EXTENDED)),
      ("ctrl_relay", "RadarState_CtrlRelayCfg", 0),
      ("sort_index", "RadarState_SortIndex", 1),
      ("rcs_threshold", "RadarState_RCS_Threshold", 0),
      ("radar_power", "RadarState_RadarPowerCfg", 0),
      ("max_distance", "RadarState_MaxDistanceCfg", ARS408_MAX_DISTANCE),
    )
    config_mismatches = tuple(
      (label, int(state[field]), expected)
      for label, field, expected in config_expectations
      if int(state[field]) != expected
    )
    wrong_config = bool(config_mismatches)

    ret.errors.radarUnavailableTemporary = temporary_fault
    ret.errors.radarFault = hard_fault
    # Allow the radar's persisted configuration and state output to settle
    # after power-up before reporting a configuration fault.
    ret.errors.wrongConfig = wrong_config and self.radar_state_frames >= CONFIG_GRACE_STATE_FRAMES
    fault_signature = (temporary_fault, hard_fault, config_mismatches, self.interference_frames,
                       self.radar_state_frames < CONFIG_GRACE_STATE_FRAMES,
                       int(state["RadarState_MotionRxState"]))
    if fault_signature != self.last_fault_signature:
      log.warning(" ".join(("ARS408 state diagnostic: interference=%d interference_frames=%d temperature=%d temporary=%d voltage=%d persistent=%d",
                            "sensor_id=%d output_type=%d quality=%d extended=%d motion_rx=%d max_distance=%d config_grace=%d")),
                  int(state["RadarState_Interference"]), self.interference_frames, int(state["RadarState_Temperature_Error"]),
                  int(state["RadarState_Temporary_Error"]), int(state["RadarState_Voltage_Error"]),
                  int(state["RadarState_Persistent_Error"]), int(state["RadarState_SensorID"]),
                  int(state["RadarState_OutputTypeCfg"]), int(state["RadarState_SendQualityCfg"]),
                  int(state["RadarState_SendExtInfoCfg"]), int(state["RadarState_MotionRxState"]),
                  int(state["RadarState_MaxDistanceCfg"]),
                  int(self.radar_state_frames < CONFIG_GRACE_STATE_FRAMES))
      if ret.errors.wrongConfig:
        log.error("ARS408 wrong configuration: %s",
                  ", ".join(f"{name}=actual:{actual}/expected:{expected}"
                            for name, actual, expected in config_mismatches))
      self.last_fault_signature = fault_signature

  def _decode_cycle(self, timestamp):
    self.rcp.update([(timestamp, self.cycle_frames)])
    core_decode_fields = {
      ARS408_GENERAL: (
        "Obj_ID", "Obj_DistLong", "Obj_DistLat", "Obj_VrelLong", "Obj_VrelLat", "Obj_RCS", "Obj_DynProp"),
      ARS408_QUALITY: ("Obj_ID", "Obj_ProbOfExist", "Obj_MeasState"),
    }

    decoded_parts = {}
    for address, fields in core_decode_fields.items():
      message_name = ARS408_MESSAGES[address][1]
      values = self.rcp.vl_all[message_name]
      columns = [values[field] for field in fields]
      if len({len(column) for column in columns}) != 1:
        return None

      rows = {}
      for row in zip(*columns, strict=True):
        rows[int(row[0])] = dict(zip(fields[1:], row[1:], strict=True))
      decoded_parts[address] = rows

    # A shared CAN bus can lose one lower-priority Quality frame without
    # invalidating every other target. Only merge IDs present in both core
    # messages; the caller applies a short grace period to missing IDs.
    objects = {}
    core_ids = set(decoded_parts[ARS408_GENERAL]) & set(decoded_parts[ARS408_QUALITY])
    for object_id in core_ids:
      objects[object_id] = decoded_parts[ARS408_GENERAL][object_id] | decoded_parts[ARS408_QUALITY][object_id]

    # Extended object frames have the lowest CAN priority in the ARS408
    # object list. Under high target load the radar can begin its next cycle
    # before every Extended frame is transmitted. General and Quality remain
    # sufficient for safe lead tracking, so only merge Extended data when the
    # complete set belongs to this cycle.
    if self._extended_complete():
      fields = ("Obj_ID", "Obj_ArelLong", "Obj_Class")
      values = self.rcp.vl_all[ARS408_MESSAGES[ARS408_EXTENDED][1]]
      columns = [values[field] for field in fields]
      if all(len(column) == self.expected_objects for column in columns):
        for row in zip(*columns, strict=True):
          obj = objects.get(int(row[0]))
          if obj is not None:
            obj.update(dict(zip(fields[1:], row[1:], strict=True)))

    return objects

  def _build_result(self, timestamp):
    if self.cycle_invalid:
      return self._incomplete_result()

    cycle_objects = self._decode_cycle(timestamp)
    if cycle_objects is None:
      return self._incomplete_result()

    if not self._cycle_complete():
      self.incomplete_cycles += 1
      if self.incomplete_cycles == 1 or self.incomplete_cycles - self.last_logged_incomplete >= LOG_EVERY_CYCLES:
        log.warning("ARS408 partial cycle salvaged: expected=%d general=%d quality=%d usable_pairs=%d consecutive=%d",
                    self.expected_objects, self.part_counts[ARS408_GENERAL], self.part_counts[ARS408_QUALITY],
                    len(cycle_objects), self.incomplete_cycles)
        self.last_logged_incomplete = self.incomplete_cycles
    else:
      self.incomplete_cycles = 0
      self.last_logged_incomplete = 0
    ret = structs.RadarData()
    if not self.rcp.can_valid:
      ret.errors.canError = True
    self._apply_radar_state_errors(ret)

    current_targets = set()
    for object_id, obj in cycle_objects.items():
      d_rel = float(obj["Obj_DistLong"])
      y_rel = -float(obj["Obj_DistLat"])
      v_rel = float(obj["Obj_VrelLong"])
      yv_rel = float(obj["Obj_VrelLat"])

      rejection_reason = object_rejection_reason(obj, object_id in self.pts)
      if rejection_reason is not None:
        self.last_rejection_reasons[object_id] = rejection_reason
        continue

      current_targets.add(object_id)
      self.track_miss_counts[object_id] = 0
      self.last_rejection_reasons.pop(object_id, None)
      if object_id not in self.pts:
        self.pts[object_id] = structs.RadarData.RadarPoint()
        self.pts[object_id].trackId = object_id

      point = self.pts[object_id]
      point.dRel = d_rel
      point.yRel = y_rel
      point.vRel = v_rel
      point.vLead = point.vRel + self.v_ego
      # Missing Extended data must never reuse acceleration from an older
      # cycle. A neutral value lets the downstream tracker estimate motion
      # from successive General frames without invalidating the radar stream.
      point.aRel = float(obj.get("Obj_ArelLong", 0.0))
      point.yvRel = yv_rel
      point.measured = int(obj["Obj_MeasState"]) in (1, 2, 5)
      # Preserve the ARS408 classification through liveTracks. Extended
      # frames may be dropped under bus load, so never turn missing data into
      # class 0 (Point); 7 is the protocol's reserved/unknown value.
      point.objectClass = int(obj.get("Obj_Class", 7))

    for object_id in list(self.pts):
      if object_id not in current_targets:
        missed_cycles = self.track_miss_counts.get(object_id, 0) + 1
        self.track_miss_counts[object_id] = missed_cycles
        if missed_cycles <= ARS408_TRACK_GRACE_CYCLES:
          # Mirror Toyota's valid-count hysteresis: a one-frame confidence or
          # list-size fluctuation must not destroy and recreate a real track.
          self.pts[object_id].measured = False
        else:
          self.last_rejection_reasons[object_id] = object_rejection_reason({}, timed_out=True)
          del self.pts[object_id]
          self.track_miss_counts.pop(object_id, None)

    # Monitor mode keeps decoding and diagnostics active but never feeds tracks
    # into radard/lead fusion. Raw object count remains available to the UI.
    ret.points = [] if self.radar_mode == 1 else list(self.pts.values())
    self._apply_missing_can_error(ret)
    if self.radar_mode == 3:
      log.debug("ARS408 debug: raw=%d accepted=%d tracked=%d rejections=%s",
                self.expected_objects, len(current_targets), len(self.pts), self.last_rejection_reasons)
    return ret

  def update(self, can_packets):
    if self.rcp is None:
      return super().update(None)

    self.update_count += 1
    result = None
    for timestamp, frames in can_packets:
      for address, data, src in frames:
        if src == ARS408_BUS and address == ARS408_RADAR_STATE and len(data) == 8:
          self._update_radar_state(timestamp, data, src)
          continue
        if src != ARS408_BUS or address not in ARS408_MESSAGES:
          continue

        base_address, _message_name, expected_dlc = ARS408_MESSAGES[address]
        if len(data) != expected_dlc:
          if self.cycle_started and address != ARS408_EXTENDED:
            self.cycle_invalid = True
          continue

        # CANParser uses the unshifted DBC addresses. Only frames that passed
        # the real SensorID 5 address and exact DLC checks reach the decoder.
        frame = (base_address, data, src)
        if address == ARS408_STATUS:
          self.last_status_update = self.update_count
          if self.cycle_started:
            cycle_result = self._build_result(timestamp)
            if cycle_result is not None:
              result = cycle_result
          self.rcp.update([(timestamp, [frame])])
          self._start_cycle()
          continue

        if not self.cycle_started:
          continue

        self._add_detail_frame(address, frame, data[0])

    if result is not None:
      return result

    missing_result = structs.RadarData()
    if self._apply_missing_can_error(missing_result) and self.update_count % ARS408_ERROR_PUBLISH_INTERVAL == 0:
      return missing_result
    return None
