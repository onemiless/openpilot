from types import SimpleNamespace

from cereal import car

from openpilot.selfdrive.debug.tesla_turn_signal_test import validation_guard


def make_state():
  CS = SimpleNamespace(
    gearShifter=car.CarState.GearShifter.park,
    standstill=True,
    vEgo=0.0,
    brakePressed=True,
    cruiseState=SimpleNamespace(enabled=False),
  )
  CC = SimpleNamespace(enabled=False, latActive=False, longActive=False)
  return CS, CC


def test_validation_guard_accepts_parked_brake_held_vehicle():
  CS, CC = make_state()
  assert validation_guard(CS, CC) is None


def test_validation_guard_blocks_motion_and_active_controls():
  CS, CC = make_state()
  CS.gearShifter = car.CarState.GearShifter.drive
  assert validation_guard(CS, CC) == "vehicle is not in Park"

  CS, CC = make_state()
  CS.vEgo = 0.2
  assert validation_guard(CS, CC) == "vehicle is not stationary"

  CS, CC = make_state()
  CS.brakePressed = False
  assert validation_guard(CS, CC) == "brake pedal is not pressed"

  CS, CC = make_state()
  CC.enabled = True
  assert validation_guard(CS, CC) == "openpilot/sunnypilot controls are active"
