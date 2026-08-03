import trace
from typing import Set, Dict, Tuple, List, Optional
from opendbc.can.parser import CANParser
from opendbc.car.interfaces import RadarInterfaceBase
from opendbc.car.structs import RadarData

# from openpilot.selfdrive.car.continental.radar_info_tx import RadarInfoTx
from common.swaglog import cloudlog
from typing import Callable, Dict, List, Tuple, Optional

# Continental ARS408 radar configuration
DBC_NAME = "ARS408"
RADAR_BUS = 5
TRIGGER_MSG_ADDR = 1546  # Obj_0_Status (0x60A)

NOT_SEEN_INIT = 33*5

# Custom CAN log configuration
LOG_FILE_PATH = "/data/log/ars408_can.log"


CMD_60A = 0x60A  #
CMD_60B = 0x60B  #
CMD_60C = 0x60C  #
CMD_60D = 0x60D  #
CMD_60E = 0x60E  #
CMD_201 = 0x201  #

CANFrame = tuple[int, bytes, int]


def _create_radar_can_parser():
  # message name with expected frequency (Hz)
  # ARS408 object list cycles every ~70-80 ms => ~13-14 Hz
  messages = [
    ("Obj_0_Status", 0),
    ("Obj_1_General", 0),
    ("Obj_2_Quality", 0),
    ("Obj_3_Extended", 0),
    # ("Obj_4_Warning", 14),
    ("RadarState", 1),  # Spec: 1 Hz (0x201)
  ]

  return CANParser(DBC_NAME, messages, RADAR_BUS)


class RadarSerialSM:
  STATE_IDLE = "IDLE"
  STATE_RECEIVING = "RECEIVING"  
  STATE_ERROR = "ERROR"

  def __init__(self):
    self.current_state = self.STATE_IDLE

    self.current_frame: List[CANFrame] = []

    # self.counter: Dict[int, int] = {CMD_60B: 0, CMD_60C: 0, CMD_60D: 0, CMD_60E: 0}
    self.counter: Dict[int, int] = {CMD_60B: 0, CMD_60C: 0, CMD_60D: 0}

    self.radar_status: Optional[CANFrame] = None
    self.radar_obj_info: Optional[CANFrame] = None

  def reset(self):
    self.current_frame.clear()
    self.counter = dict.fromkeys(self.counter, 0)
    self.current_state = self.STATE_IDLE
    self.radar_status = None
    self.radar_obj_info = None

  def _is_counter_equal(self):
    b_num = self.counter[CMD_60B]
    c_num = self.counter[CMD_60C]
    d_num = self.counter[CMD_60D]
    # e_num = self.counter[CMD_60E]
    # if b_num == c_num == d_num == e_num and b_num > 0:
    if b_num == c_num == d_num and b_num > 0:
      return b_num
    else:
      return None

  def handle_single_can_frame(self, can_frame: CANFrame):
    can_id, data, _ = can_frame
    if can_id == CMD_201:
      self.radar_status = can_frame
      return

    if self.current_state == self.STATE_ERROR:
      if can_id == CMD_60A:
        self.reset()
        self.radar_obj_info = can_frame
        self.current_frame.append(can_frame)
        self.current_state = self.STATE_RECEIVING
      return

    if self.current_state == self.STATE_IDLE:
      if can_id == CMD_60A:
        self.reset()
        self.radar_obj_info = can_frame
        self.current_frame.append(can_frame)
        self.current_state = self.STATE_RECEIVING
      return

    if self.current_state == self.STATE_RECEIVING:
      if can_id == CMD_60A:
        self.current_state = self.STATE_ERROR
        return

      if can_id in [CMD_60B, CMD_60C]:
        self.counter[can_id] += 1
        self.current_frame.append(can_frame)
        return

      # without 0x60E
      if can_id == CMD_60D:
        # if can_id == CMD_60E:
        self.counter[can_id] += 1
        self.current_frame.append(can_frame)
        # print("60B, 60B, 60C, 60D:", self.counter[CMD_60B], self.counter[CMD_60C], self.counter[CMD_60D])
        if self._is_counter_equal() is not None:
          self.current_state = self.STATE_IDLE
          if self.radar_status is not None:
            self.current_frame.append(self.radar_status)
          if self._is_counter_equal() == self.radar_obj_info[1][0]:
            return True
        return

      # self.current_state = self.STATE_ERROR
      # print(f"*** Invalid CAN ID {can_id} in RECEIVING state.")

  def handle_batch_can_frames(self, batch_frames: List[CANFrame]):
    main_id = batch_frames[0][0]  # 时间戳ID
    # complete_frame: list[CANFrame]()
    for single_frame in batch_frames[0][1]:
      if self.handle_single_can_frame(single_frame):
        return [(main_id, self.current_frame)]
    return None


class RadarInterface(RadarInterfaceBase):
  def __init__(self, CP):
    super().__init__(CP)
    self.rcp = _create_radar_can_parser()
    # self.radar_info_tx = RadarInfoTx(RADAR_BUS)
    self.radar_sm = RadarSerialSM()
    self._pts_cache = dict()
    def _extract_faults(rs: dict) -> set:
      faults = set()
      try:
        if int(rs.get("RadarState_Interference", 0)):
          faults.add("interference")
        if int(rs.get("RadarState_Temperature_Error", 0)):
          faults.add("temperatureError")
        if int(rs.get("RadarState_Temporary_Error", 0)):
          faults.add("temporaryError")
        if int(rs.get("RadarState_Persistent_Error", 0)):
          faults.add("persistentError")
        if int(rs.get("RadarState_Voltage_Error", 0)):
          faults.add("voltageError")
      except Exception:
        pass
      return faults

  def update(self, can_strings):
    if self.rcp is None:
      return super().update(None)
    # print(can_strings[0])
    if not can_strings:
      return None
    can_frames = self.radar_sm.handle_batch_can_frames(can_strings)
    if can_frames is None:
      return None
    self.rcp.update(can_frames)
    obj_status = self.rcp.vl.get("Obj_0_Status", {})
    obj_gen = self.rcp.vl_all.get("Obj_1_General", {})
    obj_qual = self.rcp.vl_all.get("Obj_2_Quality", {})
    obj_ext = self.rcp.vl_all.get("Obj_3_Extended", {})
    radar_structured_data = {
      "status": {"num_objects": obj_status.get("Obj_NofObjects", 0), "meas_counter": obj_status.get("Obj_MeasCounter", 0)},
      "objects": [],
    }

    ids_gen = obj_gen.get("Obj_ID", [])
    ids_ext = obj_ext.get("Obj_ID", [])
    ids_qual = obj_qual.get("Obj_ID", [])

    dist_long = obj_gen.get("Obj_DistLong", [])
    dist_lat = obj_gen.get("Obj_DistLat", [])
    vrel_long = obj_gen.get("Obj_VrelLong", [])
    vrel_lat = obj_gen.get("Obj_VrelLat", [])
    obj_rcs = obj_gen.get("Obj_RCS", [])
    arel_long = obj_ext.get("Obj_ArelLong", [])
    obj_class = obj_ext.get("Obj_Class", [])
    prob_exist = obj_qual.get("Obj_ProbOfExist", [])
    meas_state = obj_qual.get("Obj_MeasState", [])

    gen_id_to_idx = {obj_id: idx for idx, obj_id in enumerate(ids_gen)}
    ext_id_to_idx = {obj_id: idx for idx, obj_id in enumerate(ids_ext)}
    qual_id_to_idx = {obj_id: idx for idx, obj_id in enumerate(ids_qual)}

    all_obj_ids = set(ids_gen) | set(ids_ext) | set(ids_qual)

    self._pts_cache.clear()
    for obj_id in all_obj_ids:
      obj_data = {
        "id": obj_id,
        "distance": {"longitudinal": None, "lateral": None},
        "velocity": {"longitudinal": None, "lateral": None},
        "acceleration": {"longitudinal": None},
        "classification": None,
        "probability": None,
        "measurement_state": None,
        "RCS": None,
      }

      if obj_id in gen_id_to_idx:
        idx = gen_id_to_idx[obj_id]
        obj_data["distance"]["longitudinal"] = round(dist_long[idx], 3)
        obj_data["distance"]["lateral"] = round(-dist_lat[idx], 3)
        obj_data["velocity"]["longitudinal"] = round(vrel_long[idx], 3)
        obj_data["velocity"]["lateral"] = round(vrel_lat[idx], 3)
        obj_data["RCS"] = round(float(obj_rcs[idx]), 3)
      if obj_id in ext_id_to_idx:
        idx = ext_id_to_idx[obj_id]
        obj_data["acceleration"]["longitudinal"] = round(arel_long[idx], 3)
        obj_data["classification"] = obj_class[idx]

      if obj_id in qual_id_to_idx:
        idx = qual_id_to_idx[obj_id]
        obj_data["probability"] = prob_exist[idx]
        obj_data["measurement_state"] = meas_state[idx]

      radar_structured_data["objects"].append(obj_data)

    print("------------------------------", radar_structured_data)
    print("------------------------------", self.frame)

    for obj in radar_structured_data['objects']:
      track_id = obj['id']
      d_rel = obj['distance']['longitudinal']
      y_rel = obj['distance']['lateral']
      obj_class = obj['classification']
      prob_exist = obj['probability']
      meas_state = obj['measurement_state']
      object_rcs = obj['RCS']
      if obj_class == 0:
        continue

      if prob_exist <= 1:
        continue

      if abs(y_rel) > 3.0:
        continue

      if object_rcs < -5:
        continue
      if d_rel < 2. and abs(y_rel) > 2:
        continue

      if track_id not in self._pts_cache:
        self._pts_cache[track_id] =  RadarData.RadarPoint()
        self._pts_cache[track_id].trackId = track_id

    #  self._pts_not_seen[track_id] = NOT_SEEN_INIT
      self._pts_cache[track_id].yvRel = float(obj['velocity']['lateral'])
      self._pts_cache[track_id].dRel = d_rel
      self._pts_cache[track_id].yRel = y_rel
      self._pts_cache[track_id].vRel = float(obj['velocity']['longitudinal'])
      self._pts_cache[track_id].vLead = self._pts_cache[track_id].vRel + self.v_ego
      self._pts_cache[track_id].aRel = float(obj['acceleration']['longitudinal'])
      self._pts_cache[track_id].measured = True if meas_state >= 1 else False

    ret = RadarData()
    ret.points = list(self._pts_cache.values())
    return ret
