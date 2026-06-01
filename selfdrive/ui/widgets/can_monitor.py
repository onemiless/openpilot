import os, time
import pyray as rl
import cereal.messaging as messaging
from openpilot.common.params import Params
from openpilot.system.ui.widgets import Widget

MAX_LINES = 8
LOG_DIR = "/data/media/0/realdata"
TITLE_FONT = 44
SEC_FONT = 30
ITEM_FONT = 24
VAL_FONT = 30
COL_W = 480
ROW_H = 64
PAD = 6
GAP = 4

CATEGORIES = {
  "Drivetrain": ["DI_speed","DI_systemStatus","DI_systemPower","DI_systemLimits",
                 "DI_chassisControl","DI_torque","DI_gear","DI_vehicleSpeed",
                 "DI_brakePedalState","DI_vehicleAcceleration","DI_accelPedalPos"],
  "Battery": ["BMS_energyStatus","BMS_socStatus","BMS_powerAvailable",
              "BMS_thermalStatus","BMS_status","BMS_info","BMS_kwhCounter"],
  "Chassis": ["ESP_status","ESP_brakeApply","ESP_driverBrakeApply",
              "IBST_status","EPAS3S_sysStatus","EPAS3S_handsOnLevel"],
  "Autopilot": ["DAS_control","DAS_status","DAS_fusedSpeedLimit",
                "DAS_autopilotState","DAS_accState","DAS_autopilotHandsOnState",
                "DAS_forwardCollisionWarning","DAS_blindSpotRearLeft"],
  "Controls": ["SCCM_steeringAngleSensor","SCCM_steeringAngle","SCCM_leftStalk",
               "SCCM_rightStalk","SCCM_info","UI_cruiseControl"],
  "Climate": ["HVAC_status","VCRIGHT_hvacStatus","VCRIGHT_hvacRequest",
              "VCFRONT_coolant","VCRIGHT_thsStatus"],
  "Body": ["VCRIGHT_doorStatus","VCLEFT_doorStatus","VCFRONT_LVPowerState",
           "GTW_carConfig","UI_alertMatrix1","UI_vehicleControl"],
  "Other": []
}

FRAME_COLORS = {
  "Drivetrain": rl.Color(100, 255, 150, 240),
  "Battery": rl.Color(255, 200, 100, 240),
  "Chassis": rl.Color(255, 150, 100, 240),
  "Autopilot": rl.Color(100, 200, 255, 240),
  "Controls": rl.Color(200, 150, 255, 240),
  "Climate": rl.Color(100, 255, 200, 240),
  "Body": rl.Color(180, 180, 200, 240),
  "Other": rl.Color(140, 140, 160, 200),
}


def _decode_signal(data, sig) -> float:
  bo, bs = sig.start_bit, sig.size
  if bs == 0: return 0
  val = 0
  for i in range(bs):
    bi = (bo + i) // 8
    bbi = (bo + i) % 8
    if bi < len(data) and (data[bi] >> bbi) & 1:
      val |= (1 << i)
  if sig.is_signed and (val >> (bs - 1)):
    val -= (1 << bs)
  return val * sig.factor + sig.offset


class CanMonitorWidget(Widget):
  def __init__(self):
    super().__init__()
    self._sm = messaging.SubMaster(['can'])
    self._dbc = None
    self._dbc2 = None
    self._frame = 0
    self._recording = False
    self._log_file = None
    self._logged_addrs: set[int] = set()
    self._vals: dict[str, str] = {}
    self._frames_seen: dict[str, float] = {}
    self._by_cat: dict[str, list[str]] = {}
    self._log_lines: list[str] = []

  def _load_dbc(self):
    if self._dbc is not None: return
    try:
      from opendbc.can.dbc import DBC
      from opendbc import DBC_PATH
      self._dbc = DBC(f"{DBC_PATH}/tesla_model3_party.dbc")
      s = f"{DBC_PATH}/tesla_model3_party_supplement.dbc"
      if os.path.exists(s): self._dbc2 = DBC(s)
    except Exception:
      self._dbc = False

  def _dbc_for(self, addr):
    for d in [self._dbc2, self._dbc]:
      if isinstance(d, object) and hasattr(d, 'addr_to_msg') and addr in d.addr_to_msg:
        return d
    return None

  def _start_logging(self):
    if self._log_file: return
    try:
      os.makedirs(LOG_DIR, exist_ok=True)
      ts = time.strftime("%Y%m%d_%H%M%S")
      self._log_file = open(f"{LOG_DIR}/can_dump_{ts}.log", "w")
      self._log_file.write(f"# CAN Dump started {ts}\n# format: timestamp addr#data src\n")
      self._logged_addrs = set()
      self._recording = True
    except Exception:
      self._log_file = None
      self._recording = False

  def _stop_logging(self):
    if self._log_file:
      self._log_file.close()
      self._log_file = None
    self._recording = False

  def _cat_for(self, name):
    for cat, names in CATEGORIES.items():
      if name in names: return cat
    return "Other"

  def _update(self):
    self._load_dbc()
    self._sm.update(0)
    if not self._sm.updated['can']: return

    now = time.monotonic()
    # Clear frame age tracking
    for k in list(self._frames_seen):
      if now - self._frames_seen[k] > 3.0:
        del self._frames_seen[k]

    for can_msg in self._sm['can']:
      addr = can_msg.address
      dat = can_msg.dat
      src = can_msg.src

      if self._recording and self._log_file:
        hs = dat.hex()
        self._log_file.write(f"{now:.6f} {addr:03X}#{hs} src={src}\n")
        if addr not in self._logged_addrs:
          self._logged_addrs.add(addr)
          self._log_file.write(f"# NEW ADDR: {addr:03X} ({addr})\n")
          self._log_file.flush()

      dbc = self._dbc_for(addr)
      if dbc:
        msg_name = dbc.addr_to_msg[addr].name
        self._frames_seen[msg_name] = now
        for sn, sig in dbc.addr_to_msg[addr].sigs.items():
          try:
            rv = _decode_signal(dat, sig)
            for v in dbc.vals:
              if v.address == addr and v.name == sn:
                pd = v.def_val.split()
                vs = [int(x) for x in pd[::2]]
                ds = pd[1::2]
                mp = dict(zip(vs, ds))
                iv = int(rv)
                self._vals[sn] = mp.get(iv, f"{rv:.1f}")
                break
            else:
              self._vals[sn] = f"{rv:.1f}"
          except Exception:
            pass
      else:
        self._log_lines.append(f"{addr:03X}#{dat[:4].hex()}")

    # Categorize frames
    self._by_cat = {}
    for name, ts_val in self._frames_seen.items():
      cat = self._cat_for(name)
      if cat not in self._by_cat:
        self._by_cat[cat] = []
      self._by_cat[cat].append(name)

    if len(self._log_lines) > MAX_LINES:
      self._log_lines = self._log_lines[-MAX_LINES:]

  def _render_item(self, x, y, w, label, value, color=None):
    c = color or rl.Color(200, 200, 200, 230)
    rl.draw_text(label, x + PAD, y, ITEM_FONT, rl.Color(140, 140, 160, 220))
    rl.draw_text(value, x + PAD, y + 26, VAL_FONT, c)

  def _render(self, rect: rl.Rectangle):
    self._rect = rect
    self._frame += 1
    if self._frame % 2 == 0: self._update()

    rl.draw_rectangle(int(rect.x), int(rect.y), int(rect.width), int(rect.height),
                      rl.Color(15, 15, 35, 235))

    # Title
    if self._recording:
      title, tc = "CAN Dashboard [REC]", rl.Color(255, 50, 50, 255)
    elif self._vals:
      title, tc = "CAN Dashboard", rl.Color(100, 255, 100, 220)
    else:
      title, tc = "CAN Dashboard (no data)", rl.Color(100, 255, 100, 200)
    rl.draw_text(title, int(rect.x + 10), int(rect.y + 6), TITLE_FONT, tc)

    mp = rl.get_mouse_position()
    if rl.is_mouse_button_pressed(rl.MouseButton.MOUSE_BUTTON_LEFT):
      ty = self._rect.y + 6
      if ty <= mp.y <= ty + 48:
        if self._recording: self._stop_logging()
        else: self._start_logging()

    y = int(rect.y + 58)
    x1 = int(rect.x + 8)
    x2 = x1 + COL_W + 16
    x3 = x2 + COL_W + 16

    order = ["Drivetrain", "Battery", "Chassis", "Autopilot", "Controls", "Climate", "Body", "Other"]
    cols = [(x1, y), (x2, y), (x3, y)]
    ci = 0

    for cat in order:
      if cat not in self._by_cat or not self._by_cat[cat]:
        continue
      cx, cy = cols[ci % 3]
      fc = FRAME_COLORS.get(cat, FRAME_COLORS["Other"])
      rl.draw_text(cat, cx, cy, SEC_FONT, fc)
      cy += 34

      # Show key signals for this category
      shown = set()
      for name in self._by_cat[cat]:
        # Show 1 key value per frame if available
        for sn_prefix in name.split('_')[:2]:
          prefix = sn_prefix + "_"
          for k, v in self._vals.items():
            if k.startswith(prefix) and k not in shown:
              short = k.replace(name + "_", "").replace("_", " ")
              self._render_item(cx, cy, COL_W - 10, short, str(v), fc)
              shown.add(k)
              cy += ROW_H
              break
        if not shown:
          self._render_item(cx, cy, COL_W - 10, name, "active", fc)
          cy += ROW_H

      cols[ci % 3] = (cx, cy + GAP)
      ci += 1

    # Bottom unknown log
    log_y = max(cols[0][1], cols[1][1], cols[2][1]) + 10
    visible = max(0, int((rect.height - log_y + rect.y) / 18))
    show = self._log_lines[-visible:] if self._log_lines and visible > 0 else []
    for i, line in enumerate(show[:8]):
      yp = log_y + i * 18
      if yp < rect.y + rect.height - 6:
        rl.draw_text(line, int(rect.x + 10), yp, 14, rl.Color(140, 140, 160, 180))
