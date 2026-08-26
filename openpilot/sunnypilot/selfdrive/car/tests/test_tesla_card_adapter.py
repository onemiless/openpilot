import time
from types import SimpleNamespace

from opendbc.sunnypilot.car.tesla.values import TeslaSafetyFlagsSP
from openpilot.sunnypilot.selfdrive.car.tesla.card_adapter import CONTEXT_STALE_S, TeslaCardAdapter, speed_limit_context
from openpilot.sunnypilot.selfdrive.car.tesla.validation_controller import (
  DAS_BODY_CONTROLS_ADDRESS, decode_body_controls, tesla_body_controls_checksum,
)
from openpilot.sunnypilot.navassist.config import NavAssistParams


class FakeState:
  def __init__(self):
    self.templates = []
    self.longitudinal = []
    self.speed_limit = []

  def update_speed_button_template(self, data, mono_time):
    self.templates.append((data, mono_time))

  def update_longitudinal_context(self, *context):
    self.longitudinal.append(context)

  def update_speed_limit_target(self, *context):
    self.speed_limit.append(context)


class FakeSubMaster:
  def __init__(self, now=10.0):
    self.data = {
      "longitudinalPlanSP": SimpleNamespace(
        longitudinalPlanSource=SimpleNamespace(raw=3),
        speedLimit=SimpleNamespace(
          assist=SimpleNamespace(enabled=True),
          resolver=SimpleNamespace(speedLimitValid=True, speedLimitLastValid=False, speedLimitFinalLast=22.0),
        ),
      ),
      "carControl": SimpleNamespace(
        leftBlinker=True, rightBlinker=False, latActive=True, longActive=True,
        actuators=SimpleNamespace(accel=0.5),
      ),
      "selfdriveStateSP": SimpleNamespace(mads=SimpleNamespace(active=False)),
    }
    self.recv_time = dict.fromkeys(self.data, now)
    self.seen = dict.fromkeys(self.data, True)
    self.valid = dict.fromkeys(self.data, True)
    self.updated = dict.fromkeys(self.data, True)

  def __getitem__(self, name):
    return self.data[name]


def test_adapter_observes_only_vehicle_speed_templates():
  state = FakeState()
  adapter = TeslaCardAdapter("tesla", SimpleNamespace(CS=state), FakeSubMaster())

  adapter.observe_can([(100, [(0x3C2, b"valid", 1), (0x3C2, b"wrong-bus", 0), (0x123, b"other", 1)])])

  assert state.templates == [(b"valid", 100)]


def test_adapter_supplies_fresh_context():
  state = FakeState()
  adapter = TeslaCardAdapter("tesla", SimpleNamespace(CS=state), FakeSubMaster())

  adapter.update_context(10.0)

  assert state.longitudinal[0][0] == 3
  assert state.longitudinal[0][2] is True
  assert state.speed_limit == [(22.0, True)]


def test_adapter_invalidates_stale_context():
  state = FakeState()
  sm = FakeSubMaster()
  adapter = TeslaCardAdapter("tesla", SimpleNamespace(CS=state), sm)

  adapter.update_context(10.0 + CONTEXT_STALE_S + 0.01)

  assert state.longitudinal[0][2] is False
  assert state.speed_limit == [(0.0, False)]


def test_configured_assist_keeps_resolved_target_while_runtime_state_is_inactive():
  sm = FakeSubMaster()
  sm.data["longitudinalPlanSP"].speedLimit.assist.enabled = False

  assert speed_limit_context(sm, 10.0, assist_configured=True) == (22.0, True)


def test_non_assist_mode_never_exposes_automatic_speed_target():
  sm = FakeSubMaster()

  assert speed_limit_context(sm, 10.0, assist_configured=False) == (0.0, False)


def test_non_tesla_adapter_is_inert():
  state = FakeState()
  adapter = TeslaCardAdapter("toyota", SimpleNamespace(CS=state), FakeSubMaster())

  adapter.observe_can([(100, [(0x3C2, b"ignored", 1)])])
  adapter.update_context(10.0)

  assert not state.templates
  assert not state.longitudinal
  assert not state.speed_limit


def test_navigation_requests_tesla_turn_signal_without_direct_model_desire():
  now = time.monotonic()
  sm = FakeSubMaster(now)
  sm.data["modelV2"] = SimpleNamespace(meta=SimpleNamespace(
    laneChangeState=SimpleNamespace(raw=0), laneChangeDirection=SimpleNamespace(raw=0),
  ))
  sm.data["navAssistSP"] = SimpleNamespace(
    sessionId="session", maneuverId=7, maneuver=SimpleNamespace(raw=1), distanceToManeuverM=100.0,
    dataValid=True, guidanceValid=True, guidanceActive=True, stale=False, offRoute=False,
  )
  sm.recv_time.update(modelV2=now, navAssistSP=now)
  sm.seen.update(modelV2=True, navAssistSP=True)
  sm.valid.update(modelV2=True, navAssistSP=True)
  sm.updated.update(modelV2=True, navAssistSP=True)

  state = FakeState()
  interface = SimpleNamespace(
    CS=state,
    CP_SP=SimpleNamespace(safetyParam=int(TeslaSafetyFlagsSP.TURN_SIGNAL_VALIDATION)),
  )
  adapter = TeslaCardAdapter("tesla", interface, sm)
  adapter.nav_params = NavAssistParams(True, False, True, True, False, 1.2)

  template = bytearray([0xA5, 0x8C, 0x61, 0xB4, 0x5A, 0xC3, 0x47, 0])
  template[7] = tesla_body_controls_checksum(template)
  now_ns = time.monotonic_ns()
  adapter.validation.observe_frame(now_ns, DAS_BODY_CONTROLS_ADDRESS, bytes(template), 1)
  car_state = SimpleNamespace(vEgo=20.0, leftBlinker=False, rightBlinker=False, brakePressed=False)
  car_control = SimpleNamespace(latActive=True)

  sends = adapter.control_sends(car_state, car_control, now_ns)

  assert len(sends) == 1
  assert decode_body_controls(sends[0].dat)["turn_request"] == 1
  assert adapter.validation.status()["origin"] == "navigation"
