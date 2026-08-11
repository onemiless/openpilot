from types import SimpleNamespace

from openpilot.selfdrive.controls.controlsd import lateral_control_active


def make_car_state(*, speed=0.0, standstill=True, temporary_fault=False, permanent_fault=False):
  return SimpleNamespace(
    vEgo=speed,
    standstill=standstill,
    steerFaultTemporary=temporary_fault,
    steerFaultPermanent=permanent_fault,
  )


def test_lateral_control_respects_steer_at_standstill_capability():
  car_state = make_car_state()
  capable = SimpleNamespace(minSteerSpeed=0.0, steerAtStandstill=True)
  incapable = SimpleNamespace(minSteerSpeed=0.0, steerAtStandstill=False)

  assert lateral_control_active(True, capable, car_state)
  assert not lateral_control_active(True, incapable, car_state)
  assert lateral_control_active(True, incapable, make_car_state(speed=1.0, standstill=False))


def test_lateral_control_still_requires_authority_and_fault_free_steering():
  car_params = SimpleNamespace(minSteerSpeed=0.0, steerAtStandstill=True)

  assert not lateral_control_active(False, car_params, make_car_state())
  assert not lateral_control_active(True, car_params, make_car_state(temporary_fault=True))
  assert not lateral_control_active(True, car_params, make_car_state(permanent_fault=True))
