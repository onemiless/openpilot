import os
import time
import pyray as rl
import cereal.messaging as messaging
from openpilot.common.params import Params
from openpilot.system.ui.widgets import Widget

MAX_LINES = 30
LOG_DIR = "/data/media/0/realdata"
TITLE_FONT = 34
ITEM_FONT = 20
VALUE_FONT = 26
LINE_H = 32
COL_W = 320


def _decode_signal(data: bytes, sig) -> float:
  bit_offset = sig.start_bit
  bit_size = sig.size
  val = 0
  for i in range(bit_size):
    byte_idx = (bit_offset + i) // 8
    bit_idx = (bit_offset + i) % 8
    if byte_idx < len(data) and (data[byte_idx] >> bit_idx) & 1:
      val |= (1 << i)
  if sig.is_signed and (val >> (bit_size - 1)):
    val -= (1 << bit_size)
  return val * sig.factor + sig.offset


class CanMonitorWidget(Widget):
  def __init__(self):
    super().__init__()
    self.can_sock = messaging.sub_sock('can', conflate=True, timeout=100)
    self._dbc = None
    self._dbc2 = None
    self._frame = 0
    self._recording = False
    self._log_file = None
    self._logged_addrs: set[int] = set()

    # Dashboard values
    self._vals: dict[str, str] = {}
    self._log_lines: list[str] = []

  def _load_dbc(self):
    if self._dbc is not None:
      return
    try:
      from opendbc.can.dbc import DBC
      from opendbc import DBC_PATH
      self._dbc = DBC(f"{DBC_PATH}/tesla_model3_party.dbc")
      suppl = f"{DBC_PATH}/tesla_model3_party_supplement.dbc"
      if os.path.exists(suppl):
        self._dbc2 = DBC(suppl)
    except Exception:
      self._dbc = False

  def _dbc_for(self, addr):
    if isinstance(self._dbc2, object) and hasattr(self._dbc2, 'addr_to_msg') and addr in self._dbc2.addr_to_msg:
      return self._dbc2
    if isinstance(self._dbc, object) and hasattr(self._dbc, 'addr_to_msg') and addr in self._dbc.addr_to_msg:
      return self._dbc
    return None

  def _start_logging(self):
    if self._log_file is not None:
      return
    try:
      os.makedirs(LOG_DIR, exist_ok=True)
      ts = time.strftime("%Y%m%d_%H%M%S")
      fname = f"{LOG_DIR}/can_dump_{ts}.log"
      self._log_file = open(fname, "w")
      self._log_file.write(f"# CAN Dump started {ts}\n")
      self._log_file.write(f"# format: timestamp addr#data src\n")
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
    msgs = messaging.drain_sock(self.can_sock)
    if not msgs:
      return

    now = time.monotonic()
    for msg in msgs:
      for can_msg in msg.can:
        addr = can_msg.address
        dat = bytes(can_msg.dat)
        src = can_msg.src

        if self._recording and self._log_file:
          hex_str = dat.hex()
          self._log_file.write(f"{now:.6f} {addr:03X}#{hex_str} src={src}\n")
          if addr not in self._logged_addrs:
            self._logged_addrs.add(addr)
            self._log_file.write(f"# NEW ADDR: {addr:03X} ({addr})\n")
            self._log_file.flush()

        dbc = self._dbc_for(addr)
        if dbc:
          dbc_msg = dbc.addr_to_msg[addr]
          for sig_name, sig in dbc_msg.sigs.items():
            try:
              raw_val = _decode_signal(dat, sig)
              # Try discrete value mapping
              for v in dbc.vals:
                if v.address == addr and v.name == sig_name:
                  parts_def = v.def_val.split()
                  vals = [int(x) for x in parts_def[::2]]
                  defs = parts_def[1::2]
                  mapping = dict(zip(vals, defs))
                  int_val = int(raw_val)
                  if int_val in mapping:
                    self._vals[sig_name] = mapping[int_val]
                  else:
                    self._vals[sig_name] = f"{raw_val:.1f}"
                  break
              else:
                self._vals[sig_name] = f"{raw_val:.1f}"
            except Exception:
              pass
        else:
          label = f"{addr:03X}#{dat[:4].hex()}"
          self._log_lines.append(label)

    if len(self._log_lines) > MAX_LINES:
      self._log_lines = self._log_lines[-MAX_LINES:]

  def _render_dash_item(self, x, y, w, label, value, unit="", color=None):
    rl.draw_text(label, x + 8, y, ITEM_FONT, rl.Color(140, 140, 160, 230))
    c = color or rl.Color(0, 255, 0, 240)
    rl.draw_text(f"{value}{unit}", x + 8, y + 24, VALUE_FONT, c)

  def _render(self, rect: rl.Rectangle):
    self._rect = rect
    self._frame += 1
    if self._frame % 5 == 0:
      self._update()

    rl.draw_rectangle(int(rect.x), int(rect.y), int(rect.width), int(rect.height),
                      rl.Color(20, 20, 40, 230))

    # Title
    if self._recording:
      title = f"CAN Dashboard [REC ●]"
      title_color = rl.Color(255, 50, 50, 255)
    elif self._vals:
      title = "CAN Dashboard (tap to record)"
      title_color = rl.Color(100, 255, 100, 220)
    else:
      title = "CAN Dashboard (no data)"
      title_color = rl.Color(100, 255, 100, 200)
    rl.draw_text(title, int(rect.x + 10), int(rect.y + 6), TITLE_FONT, title_color)

    # Click detection
    mouse_pos = rl.get_mouse_position()
    if rl.is_mouse_button_pressed(rl.MouseButton.MOUSE_BUTTON_LEFT):
      title_y = self._rect.y + 6
      if title_y <= mouse_pos.y <= title_y + 42:
        if self._recording:
          self._stop_logging()
        else:
          self._start_logging()

    dash_y = int(rect.y + 44)
    col1_x = int(rect.x + 10)
    col2_x = col1_x + COL_W
    col3_x = col2_x + COL_W

    v = self._vals

    # Column 1: Steering Wheel Controls
    rl.draw_text("Controls", col1_x, dash_y, ITEM_FONT + 2, rl.Color(255, 200, 100, 240))
    self._render_dash_item(col1_x, dash_y + 28, COL_W - 10, "Left Wheel",
                           v.get("LeftWheelRoll", "-"), "", rl.Color(100, 200, 255, 240))
    self._render_dash_item(col1_x, dash_y + 84, COL_W - 10, "Right Wheel",
                           v.get("RightWheelRoll", "-"), "", rl.Color(100, 200, 255, 240))
    self._render_dash_item(col1_x, dash_y + 140, COL_W - 10, "L.Click",
                           v.get("LeftWheelClick", "-"))
    self._render_dash_item(col1_x, dash_y + 196, COL_W - 10, "R.Click",
                           v.get("RightWheelClick", "-"))

    # Column 2: Climate & Battery
    rl.draw_text("Climate/Battery", col2_x, dash_y, ITEM_FONT + 2, rl.Color(255, 200, 100, 240))
    if "InteriorTemp" in v:
      self._render_dash_item(col2_x, dash_y + 28, COL_W - 10, "Interior Temp",
                             v["InteriorTemp"], "°C", rl.Color(255, 150, 100, 240))
    else:
      self._render_dash_item(col2_x, dash_y + 28, COL_W - 10, "Interior Temp", "-", "°C")
    if "BatteryStateOfCharge" in v:
      soc = v["BatteryStateOfCharge"]
      soc_f = float(soc)
      c = rl.Color(0, 255, 0, 240) if soc_f > 20 else rl.Color(255, 100, 0, 240)
      self._render_dash_item(col2_x, dash_y + 84, COL_W - 10, "Battery SOC", soc, "%", c)
    else:
      self._render_dash_item(col2_x, dash_y + 84, COL_W - 10, "Battery SOC", "-", "%")
    self._render_dash_item(col2_x, dash_y + 140, COL_W - 10, "Battery Power",
                           v.get("BatteryPower", "-"), "kW")
    self._render_dash_item(col2_x, dash_y + 196, COL_W - 10, "Battery Current",
                           v.get("BatteryCurrent", "-"), "A")

    # Column 3: AP Status
    rl.draw_text("Autopilot", col3_x, dash_y, ITEM_FONT + 2, rl.Color(255, 200, 100, 240))
    ap = v.get("AP_Active", "0")
    ap_color = rl.Color(0, 255, 0, 240) if ap != "0" else rl.Color(140, 140, 160, 230)
    self._render_dash_item(col3_x, dash_y + 28, COL_W - 10, "AP Active", ap, "", ap_color)
    self._render_dash_item(col3_x, dash_y + 84, COL_W - 10, "AP Steering",
                           v.get("AP_Steering", "-"))
    self._render_dash_item(col3_x, dash_y + 140, COL_W - 10, "AP Speed Ctrl",
                           v.get("AP_Speed", "-"))
    self._render_dash_item(col3_x, dash_y + 196, COL_W - 10, "Hands On Wheel",
                           v.get("AP_HandsOn", "-"))

    # Bottom: scrolling unknown CAN messages
    log_y = dash_y + 260
    visible = max(1, int((rect.height - log_y + rect.y) / 20))
    show = self._log_lines[-visible:] if self._log_lines else []
    for i, line in enumerate(show):
      y_pos = log_y + i * 20
      if y_pos < rect.y + rect.height - 10:
        rl.draw_text(line, int(rect.x + 10), y_pos, 15, rl.Color(160, 160, 160, 200))
