import math

from opendbc.can import CANParser
from opendbc.car import structs
from opendbc.car.interfaces import RadarInterfaceBase


ARS408_DBC = "ARS408"
ARS408_BUS = 1
ARS408_SENSOR_ID = 5
ARS408_ADDRESS_OFFSET = ARS408_SENSOR_ID << 4

# The DBC describes SensorID 0. The radar is configured as SensorID 5 so that
# its CAN namespace does not collide with Tesla bus 1 traffic. Incoming frames
# are validated at their shifted addresses, then mapped back for DBC decoding.
ARS408_STATUS = 0x60A + ARS408_ADDRESS_OFFSET
ARS408_GENERAL = 0x60B + ARS408_ADDRESS_OFFSET
ARS408_QUALITY = 0x60C + ARS408_ADDRESS_OFFSET
ARS408_EXTENDED = 0x60D + ARS408_ADDRESS_OFFSET
ARS408_MESSAGES = {
  ARS408_STATUS: (0x60A, "Obj_0_Status", 4),
  ARS408_GENERAL: (0x60B, "Obj_1_General", 8),
  ARS408_QUALITY: (0x60C, "Obj_2_Quality", 7),
  ARS408_EXTENDED: (0x60D, "Obj_3_Extended", 8),
}
ARS408_MAX_OBJECTS = 100
MAX_INCOMPLETE_CYCLES = 5


def get_radar_can_parser(CP):
  messages = [
    ("Obj_0_Status", 14),
    ("Obj_1_General", math.nan),
    ("Obj_2_Quality", math.nan),
    ("Obj_3_Extended", math.nan),
  ]
  return CANParser(ARS408_DBC, messages, ARS408_BUS)


class RadarInterface(RadarInterfaceBase):
  def __init__(self, CP):
    super().__init__(CP)
    self.rcp = None if CP.radarUnavailable else get_radar_can_parser(CP)
    self.trigger_msg = ARS408_STATUS
    self.cycle_started = False
    self.expected_objects = 0
    self.cycle_frames = []
    self.part_ids = {address: set() for address in (ARS408_GENERAL, ARS408_QUALITY, ARS408_EXTENDED)}
    self.part_counts = {address: 0 for address in self.part_ids}
    self.cycle_invalid = False
    self.incomplete_cycles = 0

  def _start_cycle(self):
    status = self.rcp.vl["Obj_0_Status"]
    self.expected_objects = int(status["Obj_NofObjects"])
    self.cycle_frames = []
    self.part_ids = {address: set() for address in (ARS408_GENERAL, ARS408_QUALITY, ARS408_EXTENDED)}
    self.part_counts = {address: 0 for address in self.part_ids}
    self.cycle_invalid = self.expected_objects > ARS408_MAX_OBJECTS or int(status["Obj_InterfaceVersion"]) != 1
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
    if self.incomplete_cycles < MAX_INCOMPLETE_CYCLES:
      return None

    ret = structs.RadarData()
    ret.errors.canError = True
    return ret

  def _decode_cycle(self, timestamp):
    self.rcp.update([(timestamp, self.cycle_frames)])
    objects = {}
    core_decode_fields = {
      ARS408_GENERAL: (
        "Obj_ID", "Obj_DistLong", "Obj_DistLat", "Obj_VrelLong", "Obj_VrelLat", "Obj_RCS"),
      ARS408_QUALITY: ("Obj_ID", "Obj_ProbOfExist", "Obj_MeasState"),
    }

    for address, fields in core_decode_fields.items():
      message_name = ARS408_MESSAGES[address][1]
      values = self.rcp.vl_all[message_name]
      columns = [values[field] for field in fields]
      if any(len(column) != self.expected_objects for column in columns):
        return None

      for row in zip(*columns, strict=True):
        obj = objects.setdefault(int(row[0]), {})
        obj.update(dict(zip(fields[1:], row[1:], strict=True)))

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
    if not self._cycle_complete():
      return self._incomplete_result()

    cycle_objects = self._decode_cycle(timestamp)
    if cycle_objects is None or len(cycle_objects) != self.expected_objects:
      return self._incomplete_result()

    self.incomplete_cycles = 0
    ret = structs.RadarData()
    if not self.rcp.can_valid:
      ret.errors.canError = True

    current_targets = set()
    for object_id in self.part_ids[ARS408_GENERAL]:
      obj = cycle_objects[object_id]
      measurement_state = int(obj["Obj_MeasState"])
      probability = int(obj["Obj_ProbOfExist"])
      d_rel = float(obj["Obj_DistLong"])
      y_rel = -float(obj["Obj_DistLat"])
      v_rel = float(obj["Obj_VrelLong"])
      yv_rel = float(obj["Obj_VrelLat"])

      # Drop protocol invalid/deleted states and saturated or physically
      # impossible values before they can enter longitudinal lead matching.
      if measurement_state in (0, 4) or probability == 0:
        continue
      if not (0.0 <= d_rel <= 300.0 and abs(y_rel) <= 100.0 and -100.0 <= v_rel <= 100.0 and abs(yv_rel) <= 60.0):
        continue

      current_targets.add(object_id)
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
      point.measured = measurement_state in (1, 2, 5)

    for object_id in list(self.pts):
      if object_id not in current_targets:
        del self.pts[object_id]

    ret.points = list(self.pts.values())
    return ret

  def update(self, can_packets):
    if self.rcp is None:
      return super().update(None)

    result = None
    for timestamp, frames in can_packets:
      for address, data, src in frames:
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

    return result
