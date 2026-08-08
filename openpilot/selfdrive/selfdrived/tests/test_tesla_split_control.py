from openpilot.cereal import log
from openpilot.selfdrive.selfdrived.selfdrived import filter_tesla_split_control_events


EventName = log.OnroadEvent.EventName


class FakeEvents:
  def __init__(self, names):
    self.names = set(names)

  def has(self, name) -> bool:
    return name in self.names

  def remove(self, name) -> None:
    self.names.remove(name)


def test_split_control_keeps_accelerator_longitudinal_override():
  events = FakeEvents((EventName.buttonCancel, EventName.gasPressedOverride))

  filter_tesla_split_control_events(events, ap_exit_recovery_active=False)

  assert EventName.buttonCancel not in events.names
  assert EventName.gasPressedOverride in events.names
