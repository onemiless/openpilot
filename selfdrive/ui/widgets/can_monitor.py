import pyray as rl
import cereal.messaging as messaging
from openpilot.system.ui.widgets import Widget

TITLE_FONT = 50
LABEL_FONT = 36
VALUE_FONT = 64
UNIT_FONT = 34
PAD = 16
LINE_H = 120
COL_W = 520


class CanMonitorWidget(Widget):
  def __init__(self):
    super().__init__()
    self._sm = messaging.SubMaster(['can'])
    self._dbc = None
    self._dbc2 = None
    self._frame = 0
    self._vals: dict[str, str] = {}

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

  def _decode(self, data, sig) -> float:
    bo, bs = sig.start_bit, sig.size
    if bs == 0: return 0
    val = 0
    for i in range(bs):
      bi = (bo + i) // 8; bbi = (bo + i) % 8
      if bi < len(data) and (data[bi] >> bbi) & 1: val |= (1 << i)
    if sig.is_signed and (val >> (bs - 1)): val -= (1 << bs)
    return val * sig.factor + sig.offset

  def _update(self):
    self._load_dbc()
    self._sm.update(0)
    if not self._sm.updated['can']: return

    for can_msg in self._sm['can']:
      addr = can_msg.address; dat = can_msg.dat
      dbc = self._dbc_for(addr)
      if not dbc: continue
      for sn, sig in dbc.addr_to_msg[addr].sigs.items():
        try:
          rv = self._decode(dat, sig)
          for v in dbc.vals:
            if v.address == addr and v.name == sn:
              pd = v.def_val.split()
              vs = [int(x) for x in pd[::2]]; ds = pd[1::2]
              mp = dict(zip(vs, ds)); iv = int(rv)
              self._vals[sn] = mp.get(iv, f"{rv:.1f}")
              break
          else:
            self._vals[sn] = f"{rv:.1f}"
        except Exception:
          pass

  def _card(self, x, y, w, title, items, color):
    n = len(items); bh = n * LINE_H + 64
    rl.draw_rectangle(x, y, w, bh, rl.Color(18, 18, 22, 240))
    rl.draw_rectangle_lines(x, y, w, bh, color)
    rl.draw_text(title, x + PAD, y + 8, LABEL_FONT + 4, color)
    iy = y + 52
    for label, value, unit, vc in items:
      rl.draw_text(label, x + PAD, iy, LABEL_FONT, rl.Color(180, 180, 190, 240))
      vw = rl.measure_text(value, VALUE_FONT)
      uw = rl.measure_text(unit, UNIT_FONT) if unit else 0
      rl.draw_text(value, x + w - PAD - vw - uw - 10, iy + 4, VALUE_FONT, vc)
      if unit:
        rl.draw_text(unit, x + w - PAD - uw, iy + 22, UNIT_FONT, rl.Color(150, 150, 170, 220))
      iy += LINE_H

  def _render(self, rect: rl.Rectangle):
    self._rect = rect; self._frame += 1
    if self._frame % 2 == 0: self._update()

    rl.draw_rectangle(int(rect.x), int(rect.y), int(rect.width), int(rect.height), rl.BLACK)
    v = self._vals
    rl.draw_text("Vehicle Data", int(rect.x + 16), int(rect.y + 8), TITLE_FONT,
                 rl.Color(100, 255, 100, 220))
    if not v: return

    cw = COL_W; gap = 24
    cx = int(rect.x + 20); cy = int(rect.y + 70)
    white = rl.Color(255, 255, 255, 250)
    green = rl.Color(0, 255, 0, 240)
    blue = rl.Color(100, 200, 255, 240)
    orange = rl.Color(255, 180, 60, 240)
    red = rl.Color(255, 50, 50, 240)

    # Card 1: Drivetrain
    dr = []
    if "Vehicle_Speed" in v: dr.append(("Speed", v["Vehicle_Speed"], "km/h", white))
    if "Gear_Position" in v: dr.append(("Gear", v["Gear_Position"], "", blue))
    if "Drive_Mode" in v: dr.append(("Drive Mode", v["Drive_Mode"], "", blue))
    if "SteerAngle_Value" in v: dr.append(("Steering", v["SteerAngle_Value"], "deg", white))
    if "WheelPulse_FL" in v: dr.append(("Wheel Pulse", v["WheelPulse_FL"], "", white))
    if dr:
      self._card(cx, cy, cw, "Drivetrain", dr, rl.Color(0, 180, 255, 240))

    # Card 2: Traffic Light
    tl = []
    if "TL_State" in v:
      state = v["TL_State"]
      if "Red" in state: tl.append(("LIGHT", "RED", "", rl.Color(255, 30, 30, 255)))
      elif "Green" in state: tl.append(("LIGHT", "GREEN", "", rl.Color(30, 255, 30, 255)))
      elif "Yellow" in state: tl.append(("LIGHT", "YELLOW", "", rl.Color(255, 255, 30, 255)))
      else: tl.append(("LIGHT", state, "", white))
    if "TL_Countdown" in v: tl.append(("Countdown", v["TL_Countdown"], "s", blue))
    if "SLD_Distance" in v: tl.append(("Stop Line", v["SLD_Distance"], "m", blue))
    if tl:
      self._card(cx + cw + gap, cy, cw, "Traffic Light", tl, rl.Color(255, 200, 50, 240))

    cy2 = cy + max(len(dr) if dr else 1, len(tl) if tl else 1) * LINE_H + 88

    # Card 3: Battery
    bt = []
    if "Batt_Voltage" in v: bt.append(("Voltage", v["Batt_Voltage"], "V", blue))
    if "Batt_Current" in v: bt.append(("Current", v["Batt_Current"], "A", blue))
    if "Batt_SOC" in v: bt.append(("SOC", v["Batt_SOC"], "", green))
    if "Batt_Health" in v: bt.append(("Health", v["Batt_Health"], "%", green))
    if "Batt_Temp" in v: bt.append(("Temp", v["Batt_Temp"], "degC", orange))
    if bt:
      self._card(cx, cy2, cw, "Battery", bt, rl.Color(255, 180, 50, 240))

    # Card 4: GPS
    gps = []
    if "Latitude" in v: gps.append(("Lat", v["Latitude"], "deg", white))
    if "Longitude" in v: gps.append(("Lon", v["Longitude"], "deg", white))
    if gps:
      self._card(cx + cw + gap, cy2, cw, "GPS", gps, rl.Color(100, 255, 200, 240))
