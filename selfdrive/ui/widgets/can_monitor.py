import pyray as rl
import cereal.messaging as messaging
from openpilot.system.ui.widgets import Widget

MAX_LINES = 20


class CanMonitorWidget(Widget):
  def __init__(self):
    super().__init__()
    self.can_sock = messaging.sub_sock('can', conflate=True, timeout=100)
    self.messages: list[str] = []
    self._scroll_offset = 0
    self._frame = 0

  def _update_messages(self):
    msgs = messaging.drain_sock(self.can_sock)
    for msg in msgs:
      for can_msg in msg.can:
        addr = can_msg.address
        dat = can_msg.dat.hex()
        src = can_msg.src
        self.messages.append(f"{addr:03X}#{dat} src={src}")
    if len(self.messages) > MAX_LINES:
      self.messages = self.messages[-MAX_LINES:]

  def _render(self, rect: rl.Rectangle):
    self._frame += 1
    if self._frame % 5 == 0:
      self._update_messages()

    # Background
    rl.draw_rectangle(int(rect.x), int(rect.y), int(rect.width), int(rect.height),
                      rl.Color(20, 20, 40, 230))

    # Title
    font_size = 28
    title = "CAN Messages"
    if not self.messages:
      title = "CAN Messages (no data)"
    rl.draw_text(title, int(rect.x + 10), int(rect.y + 5), font_size, rl.Color(100, 255, 100, 200))

    # Messages
    line_h = 24
    start_y = int(rect.y + 40)
    visible = int((rect.height - 40) / line_h)
    show = self.messages[-visible:] if self.messages else [""]
    for i, msg in enumerate(show):
      y = start_y + i * line_h
      if y + line_h < rect.y + rect.height:
        color = rl.Color(200, 200, 200, 200) if i < len(show) - 1 else rl.Color(0, 255, 0, 255)
        rl.draw_text(msg, int(rect.x + 10), y, 20, color)
