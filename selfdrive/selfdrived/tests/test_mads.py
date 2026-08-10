from types import SimpleNamespace

from cereal import custom
from opendbc.car import structs

from openpilot.selfdrive.selfdrived.events import ET
from openpilot.selfdrive.selfdrived.mads import ModularAssistiveDrivingSystem


MadsState = custom.MadsState.State
GearShifter = structs.CarState.GearShifter
SafetyModel = structs.CarParams.SafetyModel


class FakeParams:
  def __init__(self, mads=True, steering_mode=2, user_enabled=True):
    self.values = {"Mads": mads, "MadsSteeringMode": steering_mode, "MadsUserEnabled": user_enabled}

  def get_bool(self, key):
    return bool(self.values[key])

  def get_int(self, key):
    return int(self.values[key])

  def put_bool(self, key, value):
    self.values[key] = bool(value)


class FakeEvents:
  def __init__(self, *event_types):
    self.event_types = set(event_types)

  def contains(self, event_type):
    return event_type in self.event_types


def make_car_state(**overrides):
  values = {
    "brakePressed": False,
    "gasPressed": False,
    "steeringDisengage": False,
    "invalidLkasSetting": False,
    "cruiseState": SimpleNamespace(available=True),
    "gearShifter": GearShifter.drive,
    "steerFaultTemporary": False,
    "steerFaultPermanent": False,
  }
  values.update(overrides)
  return SimpleNamespace(**values)


def make_mads(steering_mode=2):
  CP = SimpleNamespace(brand="tesla", passive=False)
  return ModularAssistiveDrivingSystem(CP, FakeParams(steering_mode=steering_mode))


def engage(mads, CS=None):
  mads.update(CS or make_car_state(), True, True, FakeEvents())
  assert mads.state == MadsState.enabled


def test_mads_keeps_lateral_active_after_normal_longitudinal_disengage():
  mads = make_mads()
  CS = make_car_state()
  engage(mads, CS)
  mads.update(CS, False, False, FakeEvents())
  assert mads.state == MadsState.enabled
  assert mads.active


def test_mads_default_brake_mode_disengages():
  mads = make_mads(steering_mode=2)
  engage(mads)
  mads.update(make_car_state(brakePressed=True), False, False, FakeEvents())
  assert mads.state == MadsState.disabled


def test_mads_remain_active_mode_keeps_lateral_after_brake():
  mads = make_mads(steering_mode=0)
  engage(mads)
  mads.update(make_car_state(brakePressed=True), False, False, FakeEvents())
  assert mads.state == MadsState.enabled
  assert mads.active


def test_mads_pause_mode_resumes_after_brake_release():
  mads = make_mads(steering_mode=1)
  engage(mads)
  mads.update(make_car_state(brakePressed=True), False, False, FakeEvents())
  assert mads.state == MadsState.paused
  mads.update(make_car_state(), False, False, FakeEvents())
  assert mads.state == MadsState.enabled


def test_mads_safety_exits_are_not_overridable():
  for CS in (make_car_state(steeringDisengage=True),
             make_car_state(brakePressed=True, gasPressed=True),
             make_car_state(invalidLkasSetting=True),
             make_car_state(cruiseState=SimpleNamespace(available=False)),
             make_car_state(gearShifter=GearShifter.park),
             make_car_state(steerFaultTemporary=True)):
    mads = make_mads(steering_mode=0)
    engage(mads)
    mads.update(CS, False, False, FakeEvents())
    assert mads.state == MadsState.disabled

  mads = make_mads(steering_mode=0)
  engage(mads)
  mads.update(make_car_state(), False, False, FakeEvents(ET.IMMEDIATE_DISABLE))
  assert mads.state == MadsState.disabled

  mads = make_mads(steering_mode=0)
  engage(mads)
  mads.update(make_car_state(), False, False, FakeEvents(ET.SOFT_DISABLE))
  assert mads.state == MadsState.disabled


def test_mads_disengages_on_panda_lateral_permission_mismatch():
  mads = make_mads()
  engage(mads)
  panda_states = [SimpleNamespace(safetyModel=SafetyModel.tesla, controlsAllowedLateral=False)]
  for _ in range(200):
    mads.data_sample(panda_states, selfdrive_enabled=False)
  assert mads.controls_mismatch
  mads.update(make_car_state(), False, False, FakeEvents())
  assert mads.state == MadsState.disabled


def test_invalid_brake_mode_fails_safe_to_disengage():
  mads = make_mads(steering_mode=99)
  engage(mads)
  mads.update(make_car_state(brakePressed=True), False, False, FakeEvents())
  assert mads.state == MadsState.disabled


def test_disabled_mads_never_claims_lateral_control():
  CP = SimpleNamespace(brand="tesla", passive=False)
  mads = ModularAssistiveDrivingSystem(CP, FakeParams(mads=False))
  mads.update(make_car_state(), True, True, FakeEvents())
  assert not mads.available
  assert not mads.enabled
  assert not mads.active


def test_runtime_feature_disable_immediately_exits_mads():
  params = FakeParams()
  CP = SimpleNamespace(brand="tesla", passive=False)
  mads = ModularAssistiveDrivingSystem(CP, params)
  engage(mads)

  params.values["Mads"] = False
  for _ in range(10):
    mads.update(make_car_state(), False, False, FakeEvents())

  assert not mads.available
  assert not mads.enabled
  assert not mads.active

  params.values["Mads"] = True
  for _ in range(10):
    mads.update(make_car_state(), True, True, FakeEvents())
  assert not mads.available
  assert not mads.enabled


def test_manual_disarm_immediately_exits_mads():
  params = FakeParams()
  CP = SimpleNamespace(brand="tesla", passive=False)
  mads = ModularAssistiveDrivingSystem(CP, params)
  engage(mads)

  params.values["MadsUserEnabled"] = False
  for _ in range(10):
    mads.update(make_car_state(), False, False, FakeEvents())

  assert not mads.enabled
  assert not mads.active


def test_manual_rearm_waits_for_normal_engagement_edge():
  params = FakeParams(user_enabled=False)
  CP = SimpleNamespace(brand="tesla", passive=False)
  mads = ModularAssistiveDrivingSystem(CP, params)

  mads.update(make_car_state(), True, True, FakeEvents())
  assert not mads.enabled

  params.values["MadsUserEnabled"] = True
  for _ in range(10):
    mads.update(make_car_state(), False, False, FakeEvents())
  assert not mads.enabled

  mads.update(make_car_state(), True, True, FakeEvents())
  assert mads.enabled
  assert mads.active
