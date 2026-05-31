import pyray as rl
import cereal.messaging as messaging
from openpilot.common.params import Params
from openpilot.system.ui.widgets import Widget

MAX_LINES = 30


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

  def _update_messages(self):
    self._load_dbc()
    msgs = messaging.drain_sock(self.can_sock)
    for msg in msgs:
      for can_msg in msg.can:
        addr = can_msg.address
        dat = bytes(can_msg.dat)
        src = can_msg.src

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

  def _render(self, rect: rl.Rectangle):
    self._frame += 1
    if self._frame % 5 == 0:
      self._update_messages()

    rl.draw_rectangle(int(rect.x), int(rect.y), int(rect.width), int(rect.height),
                      rl.Color(20, 20, 40, 230))

    font_size = 26
    title = "CAN Monitor"
    if not self.messages:
      title = "CAN Monitor (no data)"
    rl.draw_text(title, int(rect.x + 8), int(rect.y + 4), font_size, rl.Color(100, 255, 100, 200))

    line_h = 22
    start_y = int(rect.y + 36)
    visible = max(1, int((rect.height - 36) / line_h))
    show = self.messages[-visible:] if self.messages else [""]
    msg_font = 16
    for i, msg in enumerate(show):
      y = start_y + i * line_h
      if y + line_h < rect.y + rect.height:
        color = rl.Color(200, 200, 200, 220) if i < len(show) - 1 else rl.Color(0, 255, 0, 240)
        rl.draw_text(msg[:90], int(rect.x + 8), y, msg_font, color)
