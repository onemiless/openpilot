from types import SimpleNamespace

from cereal import custom
from opendbc.car import structs

from openpilot.selfdrive.selfdrived.events import ET, Events, EventName
from openpilot.selfdrive.selfdrived.mads import ModularAssistiveDrivingSystem
from openpilot.selfdrive.selfdrived.selfdrived import radar_error_event


MadsState = custom.MadsState.State
GearShifter = structs.CarState.GearShifter
SafetyModel = structs.CarParams.SafetyModel
ButtonType = structs.CarState.ButtonEvent.Type


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
  def __init__(self, *event_types, names=()):
    self.event_types = set(event_types)
    self.names = list(names)

  def contains(self, event_type):
    return event_type in self.event_types


def make_car_state(**overrides):
  values = {
    "brakePressed": False,
    "gasPressed": False,
    "steeringDisengage": False,
    "steeringOverride": False,
    "handsOnLevel": 0,
    "steeringTorque": 0.0,
    "steeringRateDeg": 0.0,
    "invalidLkasSetting": False,
    "cruiseState": SimpleNamespace(available=True),
    "gearShifter": GearShifter.drive,
    "steerFaultTemporary": False,
    "steerFaultPermanent": False,
    "eacStatus": 1,
    "eacErrorCode": 0,
    "buttonEvents": [],
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
             make_car_state(steerFaultPermanent=True),
             make_car_state(steerFaultTemporary=True, eacStatus=0, eacErrorCode=8)):
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


def test_mads_keeps_lateral_active_for_all_radar_only_soft_disables():
  for radar_event in (EventName.radarFault, EventName.radarWrongConfig, EventName.radarTempUnavailable):
    mads = make_mads(steering_mode=0)
    engage(mads)

    radar_events = FakeEvents(ET.SOFT_DISABLE, names=(radar_event,))
    mads.update(make_car_state(), False, False, radar_events)
    assert mads.state == MadsState.enabled
    assert mads.active

  mads = make_mads(steering_mode=0)
  engage(mads)
  mixed_events = FakeEvents(ET.SOFT_DISABLE, names=(EventName.radarTempUnavailable, EventName.overheat))
  mads.update(make_car_state(), False, False, mixed_events)
  assert mads.state == MadsState.disabled


def test_radar_error_mapping_pipeline_keeps_mads_lateral_active():
  error_fields = (
    ("canError", EventName.radarFault),
    ("radarFault", EventName.radarFault),
    ("wrongConfig", EventName.radarWrongConfig),
    ("radarUnavailableTemporary", EventName.radarTempUnavailable),
  )

  for error_field, expected_event in error_fields:
    radar_data = structs.RadarData()
    setattr(radar_data.errors, error_field, True)
    events = Events()
    mapped_event = radar_error_event(radar_data.errors)
    events.add(mapped_event)

    assert mapped_event == expected_event
    assert events.contains(ET.SOFT_DISABLE)
    assert not events.contains(ET.IMMEDIATE_DISABLE)

    mads = make_mads(steering_mode=0)
    engage(mads)
    mads.update(make_car_state(), False, False, events)
    assert mads.state == MadsState.enabled
    assert mads.active


def test_single_frame_eps_error_4_pauses_then_recovers_after_stable_available():
  mads = make_mads(steering_mode=0)
  engage(mads)

  transient_fault = make_car_state(steerFaultTemporary=True, eacStatus=0, eacErrorCode=4,
                                   steeringTorque=4.12, steeringRateDeg=52.0)
  mads.update(transient_fault, False, False, FakeEvents(ET.OVERRIDE_LATERAL))
  assert mads.state == MadsState.paused
  assert mads.enabled
  assert not mads.active

  recovered = make_car_state(eacStatus=1)
  for _ in range(24):
    mads.update(recovered, False, False, FakeEvents())
    assert mads.state == MadsState.paused

  mads.update(recovered, False, False, FakeEvents())
  assert mads.state == MadsState.enabled
  assert mads.active


def test_eps_error_4_recovery_timer_resets_if_fault_returns():
  mads = make_mads(steering_mode=0)
  engage(mads)
  transient_fault = make_car_state(steerFaultTemporary=True, eacStatus=0, eacErrorCode=4)
  recovered = make_car_state(eacStatus=2)

  mads.update(transient_fault, False, False, FakeEvents())
  for _ in range(24):
    mads.update(recovered, False, False, FakeEvents())
  mads.update(transient_fault, False, False, FakeEvents())
  for _ in range(24):
    mads.update(recovered, False, False, FakeEvents())
  assert mads.state == MadsState.paused

  mads.update(recovered, False, False, FakeEvents())
  assert mads.state == MadsState.enabled


def test_persistent_eps_error_4_times_out_and_disables_mads():
  mads = make_mads(steering_mode=0)
  engage(mads)
  transient_fault = make_car_state(steerFaultTemporary=True, eacStatus=0, eacErrorCode=4)

  for _ in range(99):
    mads.update(transient_fault, False, False, FakeEvents())
    assert mads.state == MadsState.paused

  mads.update(transient_fault, False, False, FakeEvents())
  assert mads.state == MadsState.disabled


def test_strong_driver_override_pauses_then_resumes_after_stable_release():
  mads = make_mads(steering_mode=0)
  engage(mads)

  mads.update(make_car_state(steeringOverride=True, handsOnLevel=3, steeringTorque=2.6,
                             steeringRateDeg=18.0), False, False, FakeEvents())
  assert mads.state == MadsState.paused
  assert mads.enabled
  assert not mads.active

  release = make_car_state(handsOnLevel=1, steeringTorque=0.2, steeringRateDeg=5.0)
  for _ in range(24):
    mads.update(release, False, False, FakeEvents())
    assert mads.state == MadsState.paused

  mads.update(release, False, False, FakeEvents())
  assert mads.state == MadsState.enabled
  assert mads.active


def test_driver_override_recovers_into_cooperative_range_without_waiting_for_hands_level_one():
  mads = make_mads(steering_mode=0)
  engage(mads)
  mads.update(make_car_state(steeringOverride=True, handsOnLevel=3, steeringTorque=2.6),
              False, False, FakeEvents())

  cooperative_release = make_car_state(handsOnLevel=2, steeringTorque=2.0, steeringRateDeg=5.0)
  for _ in range(24):
    mads.update(cooperative_release, False, False, FakeEvents())
    assert mads.state == MadsState.paused

  mads.update(cooperative_release, False, False, FakeEvents())
  assert mads.state == MadsState.enabled
  assert mads.active


def test_driver_override_release_hysteresis_resets_when_wheel_moves():
  mads = make_mads(steering_mode=0)
  engage(mads)
  mads.update(make_car_state(steeringOverride=True, handsOnLevel=3, steeringTorque=2.6),
              False, False, FakeEvents())

  release = make_car_state(handsOnLevel=1, steeringTorque=0.2, steeringRateDeg=5.0)
  for _ in range(20):
    mads.update(release, False, False, FakeEvents())
  mads.update(make_car_state(handsOnLevel=1, steeringTorque=0.2, steeringRateDeg=15.0),
              False, False, FakeEvents())
  for _ in range(24):
    mads.update(release, False, False, FakeEvents())
  assert mads.state == MadsState.paused

  mads.update(release, False, False, FakeEvents())
  assert mads.state == MadsState.enabled


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


def test_three_finger_button_toggles_mads_without_longitudinal_engagement():
  params = FakeParams(user_enabled=False)
  CP = SimpleNamespace(brand="tesla", passive=False)
  mads = ModularAssistiveDrivingSystem(CP, params)
  button = structs.CarState.ButtonEvent(type=ButtonType.lkas, pressed=True)

  mads.update(make_car_state(buttonEvents=[button]), False, False, FakeEvents())
  assert mads.enabled
  assert mads.active
  assert params.values["MadsUserEnabled"]

  mads.update(make_car_state(buttonEvents=[button]), False, False, FakeEvents())
  assert not mads.enabled
  assert not mads.active
  assert not params.values["MadsUserEnabled"]


def test_three_finger_button_cannot_enable_mads_when_cruise_main_is_unavailable():
  params = FakeParams(user_enabled=False)
  CP = SimpleNamespace(brand="tesla", passive=False)
  mads = ModularAssistiveDrivingSystem(CP, params)
  button = structs.CarState.ButtonEvent(type=ButtonType.lkas, pressed=True)

  mads.update(make_car_state(buttonEvents=[button], cruiseState=SimpleNamespace(available=False)),
              False, False, FakeEvents())
  assert not mads.enabled
  assert not params.values["MadsUserEnabled"]


def test_three_finger_button_cannot_enable_mads_while_braking():
  params = FakeParams(user_enabled=False)
  CP = SimpleNamespace(brand="tesla", passive=False)
  mads = ModularAssistiveDrivingSystem(CP, params)
  button = structs.CarState.ButtonEvent(type=ButtonType.lkas, pressed=True)

  mads.update(make_car_state(buttonEvents=[button], brakePressed=True), False, False, FakeEvents())
  assert not mads.enabled
  assert not params.values["MadsUserEnabled"]
