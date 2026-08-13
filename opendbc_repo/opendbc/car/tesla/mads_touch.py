from opendbc.car import create_button_events, structs


ButtonType = structs.CarState.ButtonEvent.Type

TESLA_UI_STATUS_2 = 0x3DF
TESLA_VEHICLE_BUS = 1
TESLA_UI_STATUS_2_LENGTH = 8
MADS_TOUCH_POINTS = 3


class MadsTouchInput:
  """Convert Tesla's center-display touch count into one LKAS button edge."""

  def __init__(self, enabled: bool):
    self.enabled = bool(enabled)
    self.touch_points = 0
    self._pending_events = []

  def set_enabled(self, enabled: bool) -> None:
    enabled = bool(enabled)
    if not enabled:
      self.touch_points = 0
      self._pending_events = []
    self.enabled = enabled

  def observe(self, address: int, data: bytes, source: int) -> None:
    if (not self.enabled or source != TESLA_VEHICLE_BUS or address != TESLA_UI_STATUS_2 or
        len(data) != TESLA_UI_STATUS_2_LENGTH):
      return

    touch_points = int(data[3])
    events = create_button_events(touch_points, self.touch_points, {MADS_TOUCH_POINTS: ButtonType.lkas})
    self._pending_events.extend(event for event in events if event.type == ButtonType.lkas)
    self.touch_points = touch_points

  def take_button_events(self):
    events = self._pending_events
    self._pending_events = []
    return events
