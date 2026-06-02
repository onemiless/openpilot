import os, time
import pyray as rl
import cereal.messaging as messaging
from openpilot.system.ui.widgets import Widget

LOG_DIR = "/data/media/0/realdata"
TITLE_FONT = 50
LABEL_FONT = 36
VALUE_FONT = 60
UNIT_FONT = 34
PAD = 16
LINE_H = 110
COL_W = 520


class CanMonitorWidget(Widget):
  def __init__(self):
    super().__init__()
    self._sm = messaging.SubMaster(['can'])
    self._dbc = None
    self._dbc2 = None
    self._frame = 0
    self._recording = False
    self._log_file = None
    self._vals: dict[str, str] = {}
    self._left_wheel = 0
    self._right_wheel = 0
    self._prev_left_raw = 0
    self._prev_right_raw = 0

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

    now = time.monotonic()
    for can_msg in self._sm['can']:
      addr = can_msg.address; dat = can_msg.dat; src = can_msg.src

      if self._recording and self._log_file:
        hs = dat.hex()
        self._log_file.write(f"{now:.6f} {addr:03X}#{hs} src={src}\n")

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

    # Track wheel scroll counts by detecting value changes
    for wn, prev_key, val_key, count_attr in [
      ("LeftWheelRoll", "_prev_left_raw", "LeftWheelRoll", "_left_wheel"),
      ("RightWheelRoll", "_prev_right_raw", "RightWheelRoll", "_right_wheel")]:
      if val_key in self._vals:
        try:
          cur = int(float(self._vals[val_key]))
          prev = getattr(self, prev_key)
          diff = cur - prev
          if diff > 0:
            setattr(self, count_attr, getattr(self, count_attr) + diff)
          elif diff < -100:  # wrap around (uint8 255→0)
            setattr(self, count_attr, getattr(self, count_attr) + (256 + diff))
          setattr(self, prev_key, cur)
        except Exception:
          pass

  def _card(self, x, y, w, title, items, color):
    n = len(items); h = n * LINE_H + 64
    rl.draw_rectangle(x, y, w, h, rl.Color(20, 20, 25, 240))
    rl.draw_rectangle_lines(x, y, w, h, color)
    rl.draw_text(title, x + PAD, y + 8, LABEL_FONT + 4, color)
    iy = y + 52
    for label, value, unit, vc in items:
      rl.draw_text(label, x + PAD, iy, LABEL_FONT, rl.Color(180, 180, 190, 240))
      vw = rl.measure_text(value, VALUE_FONT)
      uw = rl.measure_text(unit, UNIT_FONT) if unit else 0
      rl.draw_text(value, x + w - PAD - vw - uw - 10, iy + 4, VALUE_FONT, vc)
      if unit:
        rl.draw_text(unit, x + w - PAD - uw, iy + 20, UNIT_FONT, rl.Color(150, 150, 170, 220))
      iy += LINE_H

  def _render(self, rect: rl.Rectangle):
    self._rect = rect; self._frame += 1
    if self._frame % 2 == 0: self._update()

    rl.draw_rectangle(int(rect.x), int(rect.y), int(rect.width), int(rect.height), rl.BLACK)
    v = self._vals

    rl.draw_text("CAN Monitor", int(rect.x + 16), int(rect.y + 8), TITLE_FONT,
                 rl.Color(100, 255, 100, 220))
    if not v: return

    cw = COL_W; gap = 24
    cx = int(rect.x + 20); cy = int(rect.y + 70)
    white = rl.Color(255, 255, 255, 250)
    green = rl.Color(0, 255, 0, 240)
    blue = rl.Color(100, 200, 255, 240)
    orange = rl.Color(255, 200, 100, 240)
    red = rl.Color(255, 100, 100, 240)

    # Card 1: Autopilot Status
    ap = []
    if "DAS_autopilotState" in v: ap.append(("State", v["DAS_autopilotState"], "", green))
    if "DAS_accState" in v: ap.append(("ACC", v["DAS_accState"], "", green))
    if "DAS_fusedSpeedLimit" in v: ap.append(("Speed Limit", v["DAS_fusedSpeedLimit"], "km/h", blue))
    if "DAS_autopilotHandsOnState" in v: ap.append(("Hands On", v["DAS_autopilotHandsOnState"], "", orange))
    if "DAS_forwardCollisionWarning" in v: ap.append(("FCW", v["DAS_forwardCollisionWarning"], "", red))
    if ap:
      self._card(cx, cy, cw, "Autopilot", ap, rl.Color(0, 180, 255, 240))

    # Card 2: Stalk Status
    st = []
    if "LeftWheelRoll" in v: st.append(("Left Wheel", v["LeftWheelRoll"], "steps", white))
    if "RightWheelRoll" in v: st.append(("Right Wheel", v["RightWheelRoll"], "steps", white))
    if "LeftWheelClick" in v: st.append(("L.Click", v["LeftWheelClick"], "", white))
    if "RightWheelClick" in v: st.append(("R.Click", v["RightWheelClick"], "", white))
    if st:
      self._card(cx + cw + gap, cy, cw, "Controls", st, rl.Color(200, 150, 255, 240))

    # Card 3: Scroll Counts
    sc = []
    sc.append(("L Scrolls", str(self._left_wheel), "", blue))
    sc.append(("R Scrolls", str(self._right_wheel), "", blue))
    self._card(cx + cw + gap, cy + len(st) * LINE_H + 88, cw, "Scroll Counts", sc, rl.Color(255, 200, 100, 240))
