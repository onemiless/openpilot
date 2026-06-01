import os, time
import pyray as rl
import cereal.messaging as messaging
from openpilot.common.params import Params
from openpilot.system.ui.widgets import Widget

LOG_DIR = "/data/media/0/realdata"
TITLE_FONT = 50
LABEL_FONT = 34
VALUE_FONT = 56
UNIT_FONT = 32
LINE_H = 100
COL_W = 480
PAD = 12


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
      self._log_file.write(f"# CAN Dump {ts}\n")
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

  def _update(self):
    self._load_dbc()
    self._sm.update(0)
    if not self._sm.updated['can']: return

    now = time.monotonic()
    for k in list(self._frames_seen):
      if now - self._frames_seen[k] > 5.0:
        del self._frames_seen[k]

    for can_msg in self._sm['can']:
      addr = can_msg.address
      dat = can_msg.dat

      if self._recording and self._log_file:
        hs = dat.hex()
        self._log_file.write(f"{now:.6f} {addr:03X}#{hs}\n")
        if addr not in self._logged_addrs:
          self._logged_addrs.add(addr)
          self._log_file.write(f"# NEW: {addr:03X}\n")
          self._log_file.flush()

      dbc = self._dbc_for(addr)
      if not dbc: continue
      self._frames_seen[dbc.addr_to_msg[addr].name] = now
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

  def _card(self, x, y, w, title, items, color):
    """Draw a card with title and key-value items."""
    rl.draw_rectangle(x, y, w, len(items) * LINE_H + 62, rl.Color(20, 20, 25, 240))
    rl.draw_rectangle_lines(x, y, w, len(items) * LINE_H + 62, color)
    rl.draw_text(title, x + PAD, y + PAD, LABEL_FONT + 4, color)
    iy = y + 54
    for label, value, unit in items:
      rl.draw_text(label, x + PAD, iy, LABEL_FONT, rl.Color(180, 180, 190, 240))
      vw = rl.measure_text(value, VALUE_FONT)
      rl.draw_text(value, x + w - PAD - vw - (rl.measure_text(unit, UNIT_FONT) if unit else 0) - 10, iy, VALUE_FONT, rl.Color(255, 255, 255, 250))
      if unit:
        rl.draw_text(unit, x + w - PAD - rl.measure_text(unit, UNIT_FONT), iy + 16, UNIT_FONT, rl.Color(160, 160, 180, 220))
      iy += LINE_H

  def _render(self, rect: rl.Rectangle):
    self._rect = rect
    self._frame += 1
    if self._frame % 2 == 0: self._update()

    # Black background
    rl.draw_rectangle(int(rect.x), int(rect.y), int(rect.width), int(rect.height), rl.BLACK)

    v = self._vals

    # Title bar
    if self._recording:
      title = "CAN Dashboard  [REC ●]"
      tc = rl.Color(255, 80, 80, 255)
    elif v:
      title = "CAN Dashboard"
      tc = rl.Color(100, 255, 100, 240)
    else:
      title = "CAN Dashboard (no data)"
      tc = rl.Color(140, 140, 160, 220)
    rl.draw_text(title, int(rect.x + 16), int(rect.y + 8), TITLE_FONT, tc)

    # Click to record
    mp = rl.get_mouse_position()
    if rl.is_mouse_button_pressed(rl.MouseButton.MOUSE_BUTTON_LEFT):
      if self._rect.y + 8 <= mp.y <= self._rect.y + 56:
        if self._recording: self._stop_logging()
        else: self._start_logging()

    if not v:
      return

    cx = int(rect.x + 20)
    cy = int(rect.y + 70)
    cw = COL_W
    gap = 20

    # Helper: compute card height
    def ch(n_items): return n_items * LINE_H + 62 if n_items > 0 else 0

    # ── Card 1: Autopilot ──
    ap_items = []
    if "DAS_autopilotState" in v: ap_items.append(("State", v["DAS_autopilotState"], ""))
    if "DAS_fusedSpeedLimit" in v: ap_items.append(("Speed Limit", v["DAS_fusedSpeedLimit"], "km/h"))
    if "DAS_autopilotHandsOnState" in v: ap_items.append(("Hands On", v["DAS_autopilotHandsOnState"], ""))
    if "DAS_accState" in v: ap_items.append(("ACC State", v["DAS_accState"], ""))
    if "DAS_forwardCollisionWarning" in v: ap_items.append(("FCW", v["DAS_forwardCollisionWarning"], ""))
    if "DAS_blindSpotRearLeft" in v: ap_items.append(("Blind L", v["DAS_blindSpotRearLeft"], ""))
    if "DAS_blindSpotRearRight" in v: ap_items.append(("Blind R", v["DAS_blindSpotRearRight"], ""))
    if "DAS_setSpeed" in v: ap_items.append(("Set Speed", v["DAS_setSpeed"], "km/h"))
    if ap_items:
      self._card(cx, cy, cw, "Autopilot", ap_items, rl.Color(0, 180, 255, 240))

    # ── Card 2: Battery ──
    bat_items = []
    if "BMS_nominalEnergyRemaining" in v: bat_items.append(("Energy", v["BMS_nominalEnergyRemaining"], "kWh"))
    if "BMS_nominalFullPackEnergy" in v: bat_items.append(("Capacity", v["BMS_nominalFullPackEnergy"], "kWh"))
    if "BMS_energyRemainingDisplay" in v: bat_items.append(("Remaining", v["BMS_energyRemainingDisplay"], "kWh"))
    if "BatteryStateOfCharge" in v: bat_items.append(("SOC", v["BatteryStateOfCharge"], "%"))
    if "BatteryPower" in v: bat_items.append(("Power", v["BatteryPower"], "kW"))
    if "BatteryCurrent" in v: bat_items.append(("Current", v["BatteryCurrent"], "A"))
    if bat_items:
      bcy = cy + ch(len(ap_items)) + gap
      self._card(cx, bcy, cw, "Battery", bat_items, rl.Color(255, 180, 50, 240))

    # ── Card 3: Temperature ──
    tmp_items = []
    if "InteriorTemp" in v: tmp_items.append(("Interior", v["InteriorTemp"], "°C"))
    if "OutsideTemp" in v: tmp_items.append(("Outside", v["OutsideTemp"], "°C"))
    for k, val in sorted(v.items()):
      if ("temp" in k.lower() or "Temp" in k) and k not in ["InteriorTemp", "OutsideTemp"]:
        if len(tmp_items) < 6:
          tmp_items.append((k.replace("_", " "), val, "°C"))
    if tmp_items:
      self._card(cx + cw + gap, cy, cw, "Temperature", tmp_items, rl.Color(255, 120, 80, 240))

    # ── Card 4: Drivetrain ──
    di_items = []
    if "DI_vehicleSpeed" in v: di_items.append(("Speed", v["DI_vehicleSpeed"], "m/s"))
    if "DI_uiSpeed" in v: di_items.append(("Display", v["DI_uiSpeed"], ""))
    if "DI_gear" in v: di_items.append(("Gear", v["DI_gear"], ""))
    if "DI_brakePedalState" in v: di_items.append(("Brake", v["DI_brakePedalState"], ""))
    if "ESP_driverBrakeApply" in v: di_items.append(("Brake Raw", v["ESP_driverBrakeApply"], ""))
    if "DI_vehicleAcceleration" in v: di_items.append(("Accel", v["DI_vehicleAcceleration"], "m/s²"))
    if "SCCM_steeringAngle" in v: di_items.append(("Steering", v["SCCM_steeringAngle"], "°"))
    if "EPAS3S_handsOnLevel" in v: di_items.append(("Hands Lvl", v["EPAS3S_handsOnLevel"], ""))
    if di_items:
      dcy = cy + ch(len(tmp_items)) + gap
      self._card(cx + cw + gap, dcy, cw, "Drivetrain", di_items, rl.Color(100, 255, 150, 240))
