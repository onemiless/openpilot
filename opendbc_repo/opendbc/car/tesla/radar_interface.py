import math

from opendbc.can import CANParser
from opendbc.car import structs
from opendbc.car.interfaces import RadarInterfaceBase
from opendbc.car.tesla.ars408_can import (
  ARS408_BUS, ARS408_MAX_DISTANCE, ARS408_SEND_EXTENDED, ARS408_SENSOR_ID,
)
from opendbc.car.tesla.ars408_log import get_ars408_logger
from openpilot.common.params import Params

log = get_ars408_logger("radard")


ARS408_DBC = "ARS408"
ARS408_ADDRESS_OFFSET = ARS408_SENSOR_ID << 4

# The DBC describes SensorID 0. Apply the configured sensor-ID address offset
# to incoming frames, then map them back to the base DBC addresses for decode.
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
ARS408_MIN_PROBABILITY = 2       # >= 50%; distant targets commonly fluctuate below 75%
ARS408_MIN_TRACKED_PROBABILITY = 2
ARS408_TRACK_GRACE_CYCLES = 2
LOG_EVERY_CYCLES = 20
# RadarState is nominally 1 Hz. Cover the ten-second startup configuration
# window before turning a transient default configuration into a fault.
CONFIG_GRACE_STATE_FRAMES = 10
ARS408_STARTUP_GRACE_UPDATES = 1000
ARS408_STATUS_TIMEOUT_UPDATES = 50
ARS408_STATE_TIMEOUT_UPDATES = 300
ARS408_ERROR_PUBLISH_INTERVAL = 5
ARS408_EMPTY_OUTPUT_INTERVAL = 5  # card runs at 100 Hz; keep liveTracks alive at 20 Hz
ARS408_INTERFERENCE_CONFIRM_FRAMES = 10
ARS408_DUPLICATE_DREL = 1.5
ARS408_DUPLICATE_YREL = 0.6
ARS408_DUPLICATE_VREL = 1.5
ARS408_DUPLICATE_YVREL = 0.8
ARS408_HANDOVER_DREL = 2.5
ARS408_HANDOVER_YREL = 1.0
ARS408_HANDOVER_VREL = 2.5
ARS408_HANDOVER_YVREL = 1.5

def object_rejection_reason(obj, previously_tracked=False, timed_out=False, max_distance=ARS408_MAX_DISTANCE):
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
  if not (0.0 <= d_rel and math.hypot(d_rel, y_rel) <= max_distance and abs(y_rel) <= 100.0 and
          -100.0 <= v_rel <= 100.0 and abs(yv_rel) <= 60.0):
    return "out of range"

  # DynProp is not reliable enough to impose a second confidence threshold.
  # Keep its lateral corridor only to reject obvious roadside infrastructure.
  if dynamic_property in (1, 3, 5):
    if abs(y_rel) > ARS408_OBJECT_CORRIDOR:
      return "out of range"
  return None


def object_is_usable(obj, previously_tracked=False, max_distance=ARS408_MAX_DISTANCE):
  return object_rejection_reason(obj, previously_tracked, max_distance=max_distance) is None


def _object_motion(obj):
  return (
    float(obj["Obj_DistLong"]),
    -float(obj["Obj_DistLat"]),
    float(obj["Obj_VrelLong"]),
    float(obj["Obj_VrelLat"]),
  )


def _point_motion(point):
  return float(point.dRel), float(point.yRel), float(point.vRel), float(point.yvRel)


def objects_represent_same_target(first, second, handover=False):
  """Conservatively identify physically overlapping ARS408 object reports."""
  first_motion = _object_motion(first) if isinstance(first, dict) else _point_motion(first)
  second_motion = _object_motion(second) if isinstance(second, dict) else _point_motion(second)
  d_limit = ARS408_HANDOVER_DREL if handover else ARS408_DUPLICATE_DREL
  y_limit = ARS408_HANDOVER_YREL if handover else ARS408_DUPLICATE_YREL
  v_limit = ARS408_HANDOVER_VREL if handover else ARS408_DUPLICATE_VREL
  yv_limit = ARS408_HANDOVER_YVREL if handover else ARS408_DUPLICATE_YVREL

  first_class = int(first.get("Obj_Class", 7)) if isinstance(first, dict) else int(first.objectClass)
  second_class = int(second.get("Obj_Class", 7)) if isinstance(second, dict) else int(second.objectClass)
  if first_class == 7 or second_class == 7:
    # Missing Extended data removes the class discriminator. Tighten the
    # motion envelope instead of treating unknown classification as equivalent.
    d_limit *= 0.7
    y_limit *= 0.7
    v_limit *= 0.7
    yv_limit *= 0.7
  class_matches = first_class == 7 or second_class == 7 or first_class == second_class
  return class_matches and abs(first_motion[0] - second_motion[0]) <= d_limit and \
    abs(first_motion[1] - second_motion[1]) <= y_limit and abs(first_motion[2] - second_motion[2]) <= v_limit and \
    abs(first_motion[3] - second_motion[3]) <= yv_limit


def get_radar_can_parser(CP):
  messages = [
    # OutputType=disabled intentionally stops this message. The explicit
    # runtime timeout below provides the object-mode validity check.
    ("Obj_0_Status", math.nan),
    ("Obj_1_General", math.nan),
    ("Obj_2_Quality", math.nan),
    ("Obj_3_Extended", math.nan),
    ("RadarState", math.nan),
    ("FilterState_Header", math.nan),
    ("FilterState_Cfg", math.nan),
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
    self.radar_config_ready = False
    self.last_fault_signature = None
    self.radar_state_frames = 0
    self.radar_state_seq = 0
    self.filter_state_seq = 0
    self.track_miss_counts = {}
    self.update_count = 0
    self.last_status_update = None
    self.last_radar_state_update = None
    self.last_missing_can_signature = None
    self.last_rejection_reasons = {}
    self.interference_frames = 0
    self.raw_to_track_id = {}
    self.used_track_ids = set()
    self.next_track_id = 256
    self.track_handover_count = 0
    self.duplicate_suppression_count = 0
    self.last_duplicate_signature = None
    self.runtime_max_distance = ARS408_MAX_DISTANCE
    self.runtime_output_type = 1
    self.runtime_extended_enabled = ARS408_SEND_EXTENDED
    self.last_published_radar_config = None
    self.last_published_filter_state = None

  def _set_status(self, ret):
    ret.radarOnline = getattr(self, "last_radar_state_update", None) is not None and self._missing_can_signature() is None
    ret.canValid = bool(self.rcp.can_valid) and self._missing_can_signature() is None
    ret.objectCount = max(0, min(self.expected_objects, ARS408_PROTOCOL_MAX_OBJECTS)) \
      if getattr(self, "runtime_output_type", 1) == 1 else 0
    ret.mode = getattr(self, "radar_mode", 0)

  def _missing_can_signature(self):
    update_count = getattr(self, "update_count", 0)
    if update_count <= ARS408_STARTUP_GRACE_UPDATES:
      return None

    last_status_update = getattr(self, "last_status_update", None)
    last_radar_state_update = getattr(self, "last_radar_state_update", None)
    object_output = getattr(self, "runtime_output_type", 1) == 1
    status_missing = object_output and (last_status_update is None or \
                     update_count - last_status_update > ARS408_STATUS_TIMEOUT_UPDATES)
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
    ret.points = [] if self.radar_mode == 1 or not getattr(self, "radar_config_ready", False) else list(self.pts.values())
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
    self.radar_state_seq += 1
    self._update_interference_counter(state)
    self._apply_runtime_configuration(state)
    # Queue the sequence after all state values so the controller cannot see
    # a fresh sequence paired with values from the preceding RadarState frame.
    self.params.put_nonblocking("TeslaRadarStateSeq", str(self.radar_state_seq))
    self.radar_config_ready = True

  def _apply_runtime_configuration(self, state):
    max_distance = int(state["RadarState_MaxDistanceCfg"])
    output_type = int(state["RadarState_OutputTypeCfg"])
    extended_enabled = bool(int(state["RadarState_SendExtInfoCfg"]))

    if 200 <= max_distance <= 250 and max_distance % 2 == 0:
      if max_distance < getattr(self, "runtime_max_distance", ARS408_MAX_DISTANCE):
        for object_id, point in list(self.pts.items()):
          if math.hypot(float(point.dRel), float(point.yRel)) > max_distance:
            del self.pts[object_id]
            self.track_miss_counts.pop(object_id, None)
            self.raw_to_track_id.pop(object_id, None)
      self.runtime_max_distance = max_distance

    if output_type != getattr(self, "runtime_output_type", 1):
      self.pts.clear()
      self.track_miss_counts.clear()
      self.raw_to_track_id.clear()
      self.cycle_started = False
      self.expected_objects = 0
    self.runtime_output_type = output_type

    if not extended_enabled and getattr(self, "runtime_extended_enabled", True):
      for point in self.pts.values():
        point.aRel = 0.0
        point.objectClass = 7
    self.runtime_extended_enabled = extended_enabled

    snapshot = (
      max_distance, output_type, int(extended_enabled), int(state["RadarState_SendQualityCfg"]),
      int(state["RadarState_SensorID"]), int(state["RadarState_MotionRxState"]),
      int(state["RadarState_NVMReadStatus"]), int(state["RadarState_NVMwriteStatus"]),
      int(state.get("RadarState_CtrlRelayCfg", 0)), int(state.get("RadarState_RCS_Threshold", 0)),
      int(state.get("RadarState_RadarPowerCfg", 0)), int(state.get("RadarState_SortIndex", 0)),
    )
    if snapshot != getattr(self, "last_published_radar_config", None):
      keys = (
        "TeslaRadarStateMaxDistance", "TeslaRadarStateOutputType", "TeslaRadarStateExtended",
        "TeslaRadarStateQuality", "TeslaRadarStateSensorID", "TeslaRadarStateMotionRx",
        "TeslaRadarStateNVMRead", "TeslaRadarStateNVMWrite",
        "TeslaRadarStateCtrlRelay", "TeslaRadarStateRCSThreshold", "TeslaRadarStatePower", "TeslaRadarStateSort",
      )
      for key, value in zip(keys, snapshot, strict=True):
        self.params.put_nonblocking(key, str(value))
      self.last_published_radar_config = snapshot

  def _update_filter_state(self, timestamp, address, data, src):
    self.rcp.update([(timestamp, [(address, data, src)])])
    if address != 0x204:
      return

    state = self.rcp.vl["FilterState_Cfg"]
    index = int(state["FilterState_Index"])
    signal_suffixes = {
      0: "NofObj", 1: "Distance", 2: "Azimuth", 3: "VrelOncome", 4: "VrelDepart",
      5: "RCS", 6: "Lifetime", 7: "Size", 8: "ProbExists", 9: "Y", 10: "X",
      11: "VYLeftRight", 12: "VXOncome", 13: "VYRightLeft", 14: "VXDepart",
    }
    if int(state["FilterState_Type"]) != 1 or index not in signal_suffixes:
      return
    suffix = signal_suffixes[index]
    record = f"{index},{int(state['FilterState_Active'])},{float(state[f'FilterState_Min_{suffix}'])},{float(state[f'FilterState_Max_{suffix}'])}"
    if record != getattr(self, "last_published_filter_state", None):
      self.params.put_nonblocking("TeslaRadarFilterState", record)
      self.last_published_filter_state = record
    self.filter_state_seq += 1
    self.params.put_nonblocking("TeslaRadarFilterStateSeq", str(self.filter_state_seq))

  def _update_interference_counter(self, state):
    # Count independent RadarState reports, not the faster object-list results
    # that repeatedly evaluate the most recently received state.
    interference = bool(int(state["RadarState_Interference"]))
    self.interference_frames = self.interference_frames + 1 if interference else 0

  def _apply_radar_state_errors(self, ret):
    state = self.last_radar_state
    if state is None:
      return

    interference_frames = getattr(self, "interference_frames", 0)
    interference_fault = interference_frames >= ARS408_INTERFERENCE_CONFIRM_FRAMES
    temporary_fault = interference_fault or any(int(state[name]) for name in (
      "RadarState_Temperature_Error", "RadarState_Temporary_Error"))
    hard_fault = any(int(state[name]) for name in (
      "RadarState_Voltage_Error", "RadarState_Persistent_Error"))
    max_distance = int(state["RadarState_MaxDistanceCfg"])
    output_type = int(state["RadarState_OutputTypeCfg"])
    critical_config_expectations = (
      ("sensor_id", "RadarState_SensorID", ARS408_SENSOR_ID),
      ("quality", "RadarState_SendQualityCfg", 1 if output_type == 1 else int(state["RadarState_SendQualityCfg"])),
    )
    advisory_config_expectations = (
      ("ctrl_relay", "RadarState_CtrlRelayCfg", 0),
      ("sort_index", "RadarState_SortIndex", 1),
      ("rcs_threshold", "RadarState_RCS_Threshold", 0),
      ("radar_power", "RadarState_RadarPowerCfg", 0),
    )
    critical_config_mismatches = tuple(
      (label, int(state[field]), expected)
      for label, field, expected in critical_config_expectations
      if int(state[field]) != expected
    )
    advisory_config_mismatches = tuple(
      (label, int(state[field]), expected)
      for label, field, expected in advisory_config_expectations
      if int(state[field]) != expected
    )
    if output_type not in (0, 1):
      critical_config_mismatches += (("output_type", output_type, "0 or 1"),)
    if not (200 <= max_distance <= 250 and max_distance % 2 == 0):
      critical_config_mismatches += (("max_distance", max_distance, "even 200..250"),)
    wrong_config = bool(critical_config_mismatches)

    ret.errors.radarUnavailableTemporary = temporary_fault
    ret.errors.radarFault = hard_fault
    # Allow the radar's persisted configuration and state output to settle
    # after power-up before reporting a configuration fault.
    ret.errors.wrongConfig = wrong_config and self.radar_state_frames >= CONFIG_GRACE_STATE_FRAMES
    fault_signature = (temporary_fault, hard_fault, critical_config_mismatches, advisory_config_mismatches,
                       interference_frames,
                       self.radar_state_frames < CONFIG_GRACE_STATE_FRAMES,
                       int(state["RadarState_MotionRxState"]))
    if fault_signature != self.last_fault_signature:
      log.warning(" ".join(("ARS408 state diagnostic: interference=%d interference_frames=%d temperature=%d temporary=%d voltage=%d persistent=%d",
                            "sensor_id=%d output_type=%d quality=%d extended=%d motion_rx=%d max_distance=%d config_grace=%d")),
                  int(state["RadarState_Interference"]), interference_frames, int(state["RadarState_Temperature_Error"]),
                  int(state["RadarState_Temporary_Error"]), int(state["RadarState_Voltage_Error"]),
                  int(state["RadarState_Persistent_Error"]), int(state["RadarState_SensorID"]),
                  int(state["RadarState_OutputTypeCfg"]), int(state["RadarState_SendQualityCfg"]),
                  int(state["RadarState_SendExtInfoCfg"]), int(state["RadarState_MotionRxState"]),
                  int(state["RadarState_MaxDistanceCfg"]),
                  int(self.radar_state_frames < CONFIG_GRACE_STATE_FRAMES))
      if ret.errors.wrongConfig:
        log.error("ARS408 wrong configuration: %s",
                  ", ".join(f"{name}=actual:{actual}/expected:{expected}"
                            for name, actual, expected in critical_config_mismatches))
      if advisory_config_mismatches:
        log.warning("ARS408 non-critical configuration differences (radar remains available): %s",
                    ", ".join(f"{name}=actual:{actual}/recommended:{expected}"
                              for name, actual, expected in advisory_config_mismatches))
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
    if getattr(self, "runtime_extended_enabled", ARS408_SEND_EXTENDED) and self._extended_complete():
      fields = ("Obj_ID", "Obj_ArelLong", "Obj_Class")
      values = self.rcp.vl_all[ARS408_MESSAGES[ARS408_EXTENDED][1]]
      columns = [values[field] for field in fields]
      if all(len(column) == self.expected_objects for column in columns):
        for row in zip(*columns, strict=True):
          obj = objects.get(int(row[0]))
          if obj is not None:
            obj.update(dict(zip(fields[1:], row[1:], strict=True)))

    return objects

  def _ensure_tracking_state(self):
    if not hasattr(self, "raw_to_track_id"):
      self.raw_to_track_id = {raw_id: int(point.trackId) for raw_id, point in self.pts.items()}
    if not hasattr(self, "used_track_ids"):
      self.used_track_ids = set(self.raw_to_track_id.values())
    if not hasattr(self, "next_track_id"):
      self.next_track_id = max(256, max(self.used_track_ids, default=255) + 1)
    self.track_handover_count = getattr(self, "track_handover_count", 0)
    self.duplicate_suppression_count = getattr(self, "duplicate_suppression_count", 0)
    self.last_duplicate_signature = getattr(self, "last_duplicate_signature", None)

  def _allocate_track_id(self, raw_id):
    self._ensure_tracking_state()
    if raw_id not in self.used_track_ids:
      track_id = raw_id
    else:
      track_id = self.next_track_id
      self.next_track_id += 1
    self.used_track_ids.add(track_id)
    self.raw_to_track_id[raw_id] = track_id
    return track_id

  def _handoff_track(self, old_raw_id, new_raw_id, reason, old_obj, new_obj):
    point = self.pts.pop(old_raw_id)
    logical_id = self.raw_to_track_id.pop(old_raw_id, int(point.trackId))
    self.pts[new_raw_id] = point
    self.raw_to_track_id[new_raw_id] = logical_id
    self.track_miss_counts[new_raw_id] = self.track_miss_counts.pop(old_raw_id, 0)
    self.last_rejection_reasons.pop(old_raw_id, None)
    self.track_handover_count += 1
    old_motion = _object_motion(old_obj) if isinstance(old_obj, dict) else _point_motion(old_obj)
    new_motion = _object_motion(new_obj)
    log.info("ARS408 track handover reason=%s raw_old=%d raw_new=%d logical=%d dd=%.2f dy=%.2f dv=%.2f total=%d",
             reason, old_raw_id, new_raw_id, logical_id, abs(old_motion[0] - new_motion[0]),
             abs(old_motion[1] - new_motion[1]), abs(old_motion[2] - new_motion[2]), self.track_handover_count)

  @staticmethod
  def _object_rank(raw_id, obj, previously_tracked):
    state_rank = {2: 4, 5: 3, 1: 3, 3: 1}.get(int(obj["Obj_MeasState"]), 0)
    return previously_tracked, state_rank, int(obj["Obj_ProbOfExist"]), -raw_id

  def _associate_cycle_objects(self, cycle_objects):
    """Transfer changing raw IDs and suppress physically overlapping reports."""
    self._ensure_tracking_state()

    # Prefer the radar's explicit deleted-for-merge -> new-from-merge signal.
    deleted_ids = [raw_id for raw_id, obj in cycle_objects.items()
                   if int(obj["Obj_MeasState"]) == 4 and raw_id in self.pts]
    new_merge_ids = [raw_id for raw_id, obj in cycle_objects.items()
                     if int(obj["Obj_MeasState"]) == 5 and raw_id not in self.pts]
    for new_raw_id in new_merge_ids:
      candidates = [old_raw_id for old_raw_id in deleted_ids if old_raw_id in self.pts and
                    objects_represent_same_target(cycle_objects[old_raw_id], cycle_objects[new_raw_id], handover=True)]
      if candidates:
        old_raw_id = min(candidates, key=lambda raw_id: abs(_object_motion(cycle_objects[raw_id])[0] -
                                                             _object_motion(cycle_objects[new_raw_id])[0]))
        self._handoff_track(old_raw_id, new_raw_id, "merge", cycle_objects[old_raw_id], cycle_objects[new_raw_id])

    # If the old raw ID disappears without an explicit state-4 frame, reuse
    # its logical track only when the replacement is tightly colocated.
    active_cycle_ids = {raw_id for raw_id, obj in cycle_objects.items() if int(obj["Obj_MeasState"]) not in (0, 4)}
    missing_tracked_ids = [raw_id for raw_id in self.pts if raw_id not in active_cycle_ids]
    for new_raw_id in [raw_id for raw_id in active_cycle_ids if raw_id not in self.pts]:
      candidates = [old_raw_id for old_raw_id in missing_tracked_ids if old_raw_id in self.pts and
                    objects_represent_same_target(self.pts[old_raw_id], cycle_objects[new_raw_id])]
      if candidates:
        old_raw_id = min(candidates, key=lambda raw_id: abs(float(self.pts[raw_id].dRel) -
                                                             float(cycle_objects[new_raw_id]["Obj_DistLong"])))
        self._handoff_track(old_raw_id, new_raw_id, "kinematic", self.pts[old_raw_id], cycle_objects[new_raw_id])

    # Suppress only overlapping pairs where at least one raw ID is new to the
    # host. Two established tracks are never merged without radar merge state.
    suppressed = set()
    active_ids = sorted(raw_id for raw_id in active_cycle_ids if raw_id in cycle_objects)
    for index, first_id in enumerate(active_ids):
      if first_id in suppressed:
        continue
      for second_id in active_ids[index + 1:]:
        if second_id in suppressed or (first_id in self.pts and second_id in self.pts):
          continue
        if not objects_represent_same_target(cycle_objects[first_id], cycle_objects[second_id]):
          continue
        first_rank = self._object_rank(first_id, cycle_objects[first_id], first_id in self.pts)
        second_rank = self._object_rank(second_id, cycle_objects[second_id], second_id in self.pts)
        keep_id, drop_id = (first_id, second_id) if first_rank >= second_rank else (second_id, first_id)
        suppressed.add(drop_id)
        signature = (keep_id, drop_id)
        self.duplicate_suppression_count += 1
        if signature != self.last_duplicate_signature:
          keep_motion = _object_motion(cycle_objects[keep_id])
          drop_motion = _object_motion(cycle_objects[drop_id])
          log.warning("ARS408 duplicate suppressed keep_raw=%d drop_raw=%d dd=%.2f dy=%.2f dv=%.2f total=%d",
                      keep_id, drop_id, abs(keep_motion[0] - drop_motion[0]), abs(keep_motion[1] - drop_motion[1]),
                      abs(keep_motion[2] - drop_motion[2]), self.duplicate_suppression_count)
        self.last_duplicate_signature = signature

    if not suppressed:
      self.last_duplicate_signature = None
    return {raw_id: obj for raw_id, obj in cycle_objects.items() if raw_id not in suppressed}

  def _build_result(self, timestamp):
    if self.cycle_invalid:
      return self._incomplete_result()

    cycle_objects = self._decode_cycle(timestamp)
    if cycle_objects is None:
      return self._incomplete_result()
    cycle_objects = self._associate_cycle_objects(cycle_objects)

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

      rejection_reason = object_rejection_reason(obj, object_id in self.pts,
                                                 max_distance=getattr(self, "runtime_max_distance", ARS408_MAX_DISTANCE))
      if rejection_reason is not None:
        self.last_rejection_reasons[object_id] = rejection_reason
        continue

      current_targets.add(object_id)
      self.track_miss_counts[object_id] = 0
      self.last_rejection_reasons.pop(object_id, None)
      if object_id not in self.pts:
        self.pts[object_id] = structs.RadarData.RadarPoint()
        self.pts[object_id].trackId = self._allocate_track_id(object_id)

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
          self.raw_to_track_id.pop(object_id, None)

    # Monitor mode keeps decoding and diagnostics active but never feeds tracks
    # into radard/lead fusion. Raw object count remains available to the UI.
    ret.points = [] if self.radar_mode == 1 or not getattr(self, "radar_config_ready", False) or \
      getattr(self, "runtime_output_type", 1) != 1 else list(self.pts.values())
    self._apply_missing_can_error(ret)
    if self.radar_mode == 3:
      log.debug("ARS408 debug: raw=%d accepted=%d tracked=%d handovers=%d duplicates=%d rejections=%s",
                self.expected_objects, len(current_targets), len(self.pts), self.track_handover_count,
                self.duplicate_suppression_count, self.last_rejection_reasons)
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
          if self.runtime_output_type != 1:
            # Disabled output is a valid vision-only state. Unsupported Cluster
            # output follows the same empty-data fallback but reports wrongConfig.
            result = structs.RadarData()
            result.points = []
            self._apply_radar_state_errors(result)
            self._set_status(result)
          continue
        if src == ARS408_BUS and address in (0x203, 0x204) and len(data) == (2 if address == 0x203 else 5):
          self._update_filter_state(timestamp, address, data, src)
          continue
        if src != ARS408_BUS or address not in ARS408_MESSAGES:
          continue

        base_address, _message_name, expected_dlc = ARS408_MESSAGES[address]
        if len(data) != expected_dlc:
          if self.cycle_started and address != ARS408_EXTENDED:
            self.cycle_invalid = True
          continue

        # CANParser uses the unshifted DBC addresses. Only frames that passed
        # the configured SensorID 0 address and exact DLC checks reach the decoder.
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

    if self.runtime_output_type != 1 and self.update_count % ARS408_EMPTY_OUTPUT_INTERVAL == 0:
      result = structs.RadarData()
      result.points = []
      self._apply_radar_state_errors(result)
      self._apply_missing_can_error(result)
      return result

    missing_result = structs.RadarData()
    if self._apply_missing_can_error(missing_result) and self.update_count % ARS408_ERROR_PUBLISH_INTERVAL == 0:
      return missing_result
    return None
