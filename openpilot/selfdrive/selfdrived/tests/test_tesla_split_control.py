from openpilot.cereal import log
from openpilot.selfdrive.selfdrived.selfdrived import filter_tesla_coop_steering_events, filter_tesla_split_control_events


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


def test_coop_steering_override_does_not_exit_session():
  events = FakeEvents((EventName.steerDisengage, EventName.steerOverride))

  filter_tesla_coop_steering_events(events, coop_steering_enabled=True)

  assert EventName.steerDisengage not in events.names
  assert EventName.steerOverride in events.names


def test_non_coop_steering_override_still_exits_session():
  events = FakeEvents((EventName.steerDisengage,))

  filter_tesla_coop_steering_events(events, coop_steering_enabled=False)

  assert EventName.steerDisengage in events.names
