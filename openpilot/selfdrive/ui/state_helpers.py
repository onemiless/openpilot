from opendbc.car.structs import car


def onroad_ui_active(device_started: bool, ignition: bool, gear_shifter: car.CarState.GearShifter) -> bool:
  """Keep driving processes alive in Park while returning the display to settings mode."""
  return device_started and ignition and gear_shifter != car.CarState.GearShifter.park
