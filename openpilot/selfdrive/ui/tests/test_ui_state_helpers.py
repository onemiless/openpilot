from opendbc.car.structs import car

from openpilot.selfdrive.ui.state_helpers import onroad_ui_active


def test_park_returns_ui_to_settings_mode_while_vehicle_stays_started():
  assert not onroad_ui_active(True, True, car.CarState.GearShifter.park)


def test_non_park_gear_keeps_onroad_ui_active():
  assert onroad_ui_active(True, True, car.CarState.GearShifter.drive)
  assert onroad_ui_active(True, True, car.CarState.GearShifter.reverse)


def test_device_and_ignition_still_gate_onroad_ui():
  assert not onroad_ui_active(False, True, car.CarState.GearShifter.drive)
  assert not onroad_ui_active(True, False, car.CarState.GearShifter.drive)
