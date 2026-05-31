import os
import time
import pyray as rl
import cereal.messaging as messaging
from openpilot.common.params import Params
from openpilot.system.ui.widgets import Widget

MAX_LINES = 50
LOG_DIR = "/data/media/0/realdata"
TITLE_FONT = 38
MSG_FONT = 22
LINE_H = 30


def _decode_signal(data: bytes, sig) -> float:
  """Decode a single signal value from CAN data bytes."""
  # Extract bits [lsb:msb+1] — simplified big-endian extraction
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
    self.messages: list[str] = []
    self._dbc = None
    self._frame = 0
    self._recording = False
    self._log_file = None
    self._logged_addrs: set[int] = set()  # unique addresses seen

  def _load_dbc(self):
    if self._dbc is not None:
      return
    try:
      # Auto-detect car brand from params, fallback to Tesla
      from opendbc.can.dbc import DBC
      from opendbc import DBC_PATH
      cp_bytes = Params().get("CarParamsCache")
      dbc_name = "tesla_model3_party"
      if cp_bytes:
        from cereal import car
        cp = car.CarParams.from_bytes(cp_bytes)
        brand = str(cp.brand)
        brand_dbc_map = {
          "toyota": "toyota_nodsu_pt_generated",
          "honda": "honda_civic_touring_2016_can_generated",
          "hyundai": "hyundai_canfd_generated",
          "volkswagen": "volkswagen_mqb_2010",
          "ford": "ford_lincoln_base_pt",
          "gm": "gm_global_a_powertrain_generated",
          "chrysler": "chrysler_pacifica_2017_hybrid_generated",
          "rivian": "rivian_r1t_gen1",
          "subaru": "subaru_global_2017_generated",
          "mazda": "mazda_cx5_2022",
          "nissan": "nissan_x_trail_2017_generated",
        }
        dbc_name = brand_dbc_map.get(brand, dbc_name)
      self._dbc = DBC(f"{DBC_PATH}/{dbc_name}.dbc")
    except Exception:
      self._dbc = False  # mark as failed

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

  def _update_messages(self):
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

        # Log raw data
        if self._recording and self._log_file:
          hex_str = dat.hex()
          self._log_file.write(f"{now:.6f} {addr:03X}#{hex_str} src={src}\n")
          if addr not in self._logged_addrs:
            self._logged_addrs.add(addr)
            self._log_file.write(f"# NEW ADDR: {addr:03X} ({addr})\n")
            self._log_file.flush()

        # Build label: try DBC first, fall back to raw hex
        if isinstance(self._dbc, object) and hasattr(self._dbc, 'addr_to_msg') and addr in self._dbc.addr_to_msg:
          dbc_msg = self._dbc.addr_to_msg[addr]
          parts = [f"{addr:03X} {dbc_msg.name}"]
          # Show first 2 signals with values
          for i, (sig_name, sig) in enumerate(dbc_msg.sigs.items()):
            if i >= 3:  # max 3 signals per message
              break
            try:
              raw_val = _decode_signal(dat, sig)
              # Try discrete value mapping if available
              matched = False
              for v in self._dbc.vals:
                if v.address == addr and v.name == sig_name:
                  parts_def = v.def_val.split()
                  vals = [int(x) for x in parts_def[::2]]
                  defs = parts_def[1::2]
                  mapping = dict(zip(vals, defs))
                  int_val = int(raw_val)
                  if int_val in mapping:
                    parts.append(f"{sig_name}={mapping[int_val]}")
                  else:
                    parts.append(f"{sig_name}={raw_val:.1f}")
                  matched = True
                  break
              if not matched:
                parts.append(f"{sig_name}={raw_val:.1f}")
            except Exception:
              pass
          label = " | ".join(parts)
        else:
          label = f"{addr:03X}#{dat[:4].hex()} src={src}"
        self.messages.append(label)

    if len(self.messages) > MAX_LINES:
      self.messages = self.messages[-MAX_LINES:]

  def _handle_click(self, mouse_x: float, mouse_y: float):
    """Toggle recording on title bar click"""
    title_y = self._rect.y + 6
    title_h = 42
    if title_y <= mouse_y <= title_y + title_h:
      if self._recording:
        self._stop_logging()
      else:
        self._start_logging()

  def _render(self, rect: rl.Rectangle):
    self._rect = rect
    self._frame += 1
    if self._frame % 5 == 0:
      self._update_messages()

    rl.draw_rectangle(int(rect.x), int(rect.y), int(rect.width), int(rect.height),
                      rl.Color(20, 20, 40, 230))

    # Title bar with recording status
    if self._recording:
      title = f"CAN Monitor [REC ● {len(self._logged_addrs)} addrs]"
      title_color = rl.Color(255, 50, 50, 255)
    elif self.messages:
      title = "CAN Monitor (tap to record)"
      title_color = rl.Color(100, 255, 100, 220)
    else:
      title = "CAN Monitor (no data)"
      title_color = rl.Color(100, 255, 100, 200)
    rl.draw_text(title, int(rect.x + 10), int(rect.y + 6), TITLE_FONT, title_color)

    # Click detection
    mouse_pos = rl.get_mouse_position()
    if rl.is_mouse_button_pressed(rl.MouseButton.MOUSE_BUTTON_LEFT):
      self._handle_click(mouse_pos.x, mouse_pos.y)

    start_y = int(rect.y + 48)
    visible = max(1, int((rect.height - 48) / LINE_H))
    show = self.messages[-visible:] if self.messages else [""]
    for i, msg in enumerate(show):
      y = start_y + i * LINE_H
      if y + LINE_H < rect.y + rect.height:
        color = rl.Color(200, 200, 200, 230) if i < len(show) - 1 else rl.Color(0, 255, 0, 240)
        rl.draw_text(msg, int(rect.x + 10), y, MSG_FONT, color)
