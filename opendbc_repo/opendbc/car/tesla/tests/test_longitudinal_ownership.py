from types import SimpleNamespace

import pytest

from opendbc.can import CANPacker, CANParser
from opendbc.car.tesla.carcontroller import CarController, LongitudinalAction, TeslaLongitudinalOwnership
from opendbc.car.tesla.teslacan import TESLA_LONGITUDINAL_HANDOFF_AEB_EVENT, TeslaCAN


def decode_das_control(message):
  address, data, bus = message
  parser = CANParser("tesla_model3_party", [("DAS_control", 0)], bus)
  parser.update([(1_000_000_000, [(address, data, bus)])])
  return parser.vl["DAS_control"]


def controller_fixture(counter=3, long_active=True, fresh=True):
  controller = CarController.__new__(CarController)
  controller.CP = SimpleNamespace(openpilotLongitudinalControl=True)
  controller.tesla_can = TeslaCAN(CANPacker("tesla_model3_party"))
  controller.longitudinal_ownership = TeslaLongitudinalOwnership()
  controller.longitudinal_counter = None
  controller.longitudinal_handoff_nanos = 0
  controller.last_long_control_frame = -4
  controller._last_long_tx = {}
  controller._last_long_tx_echo_nanos = 0
  controller._last_long_tx_echo = {}
  controller.frame = 0
  now_nanos = 1_000_000_000
  das_control = {
    "DAS_setSpeed": 80, "DAS_accState": 4, "DAS_aebEvent": 0,
    "DAS_jerkMin": -1, "DAS_jerkMax": 1, "DAS_accelMin": 0,
    "DAS_accelMax": 0, "DAS_controlCounter": counter,
  }
  cs = SimpleNamespace(out=SimpleNamespace(vEgo=20.0, brakePressed=False), das_control=das_control,
                       das_control_nanos=now_nanos if fresh else 0)
  cc = SimpleNamespace(longActive=long_active, actuators=SimpleNamespace(accel=1.0))
  return controller, cc, cs, das_control, now_nanos


@pytest.mark.parametrize(("speed_kph", "accel"), (
  (0.25, -2.0),
  (48.95, -0.56),
  (110.3, -0.1),
  (124.6, 0.1),
))
def test_active_longitudinal_set_speed_tracks_vehicle_state(speed_kph, accel):
  tesla_can = TeslaCAN(CANPacker("tesla_model3_party"))
  message = tesla_can.create_longitudinal_command(4, accel, 1, speed_kph / 3.6, True)
  signals = decode_das_control(message)
  expected = min(max(speed_kph / 3.6 + accel, 0) * 3.6, 400)
  assert signals["DAS_setSpeed"] == pytest.approx(expected, abs=0.11)


def test_active_longitudinal_jerk_max_ramps_from_zero():
  tesla_can = TeslaCAN(CANPacker("tesla_model3_party"))
  first = decode_das_control(tesla_can.create_longitudinal_command(4, 0.0, 1, 20.0, True))
  assert first["DAS_jerkMax"] == pytest.approx(0.04, abs=0.02)
  for counter in range(2, 124):
    message = tesla_can.create_longitudinal_command(4, 0.0, counter % 8, 20.0, True)
  saturated = decode_das_control(message)
  assert saturated["DAS_jerkMax"] == pytest.approx(4.9, abs=0.02)


def test_das_control_dbc_matches_known_sp_payload():
  packer = CANPacker("tesla_model3_party")
  values = {
    "DAS_setSpeed": 47.3,
    "DAS_accState": 4,
    "DAS_aebEvent": 0,
    "DAS_jerkMin": -4.9,
    "DAS_jerkMax": 4.9,
    "DAS_accelMin": -1.6,
    "DAS_accelMax": 0,
    "DAS_controlCounter": 7,
    "DAS_controlChecksum": 0,
  }
  _, data, _ = packer.make_can_msg("DAS_control", 0, values)
  assert data.hex() == "d941a4837c7af7e9"


def test_ownership_cancel_then_release():
  ownership = TeslaLongitudinalOwnership()
  assert ownership.update(False, False) == LongitudinalAction.NONE
  assert ownership.update(True, False) == LongitudinalAction.CONTROL
  assert ownership.update(False, False) == LongitudinalAction.CANCEL
  assert ownership.update(False, False) == LongitudinalAction.RELEASE
  assert ownership.update(False, False) == LongitudinalAction.NONE


def test_controller_resyncs_counter_and_stops_acc_on_after_long_inactive():
  controller, cc, cs, _, now_nanos = controller_fixture(counter=3)
  control = controller.update_longitudinal_control(cc, cs, False, now_nanos)
  assert decode_das_control(control[0])["DAS_controlCounter"] == 4
  assert decode_das_control(control[0])["DAS_accState"] == 4

  controller.frame += 4
  cc.longActive = False
  cancel = controller.update_longitudinal_control(cc, cs, False, now_nanos + 40_000_000)
  assert decode_das_control(cancel[0])["DAS_controlCounter"] == 5
  assert decode_das_control(cancel[0])["DAS_accState"] == 13

  controller.frame += 4
  release = controller.update_longitudinal_control(cc, cs, False, now_nanos + 80_000_000)
  assert decode_das_control(release[0])["DAS_aebEvent"] == TESLA_LONGITUDINAL_HANDOFF_AEB_EVENT
  assert decode_das_control(release[0])["DAS_controlCounter"] == 5


def test_controller_requires_fresh_oem_counter_and_releases_on_brake():
  controller, cc, cs, _, now_nanos = controller_fixture(counter=2, fresh=False)
  assert controller.update_longitudinal_control(cc, cs, False, now_nanos) == []

  controller.frame += 4
  cs.das_control_nanos = now_nanos
  control = controller.update_longitudinal_control(cc, cs, False, now_nanos)
  assert decode_das_control(control[0])["DAS_controlCounter"] == 3

  controller.frame += 4
  cs.out.brakePressed = True
  cancel = controller.update_longitudinal_control(cc, cs, False, now_nanos + 40_000_000)
  assert decode_das_control(cancel[0])["DAS_accState"] == 13


def test_longitudinal_schedule_reanchors_after_off_phase_send():
  controller, cc, cs, _, now_nanos = controller_fixture(counter=2)
  controller.frame = 1
  controller.last_long_control_frame = -3
  assert len(controller.update_longitudinal_control(cc, cs, False, now_nanos)) == 1
  assert controller.last_long_control_frame == 1

  controller.frame = 4
  assert controller.update_longitudinal_control(cc, cs, False, now_nanos + 30_000_000) == []
  controller.frame = 5
  assert len(controller.update_longitudinal_control(cc, cs, False, now_nanos + 40_000_000)) == 1


def test_longitudinal_returned_echo_records_physical_interval(monkeypatch):
  controller, _, _, _, now_nanos = controller_fixture()
  controller._last_long_tx = {"tx_raw": "d941a4837c7af7e9"}
  events = []
  monkeypatch.setattr("opendbc.car.tesla.carcontroller.cloudlog.event", lambda name, **kwargs: events.append((name, kwargs)))

  data = bytes.fromhex("d941a4837c7af7e9")
  controller._observe_longitudinal_tx_echo(now_nanos, 0x2B9, data, 0x80)
  controller._observe_longitudinal_tx_echo(now_nanos + 58_000_000, 0x2B9, data, 0x80)

  assert controller._last_long_tx_echo["echo_kind"] == "tx_echo"
  assert controller._last_long_tx_echo["echo_bus"] == 0
  assert controller._last_long_tx_echo["echo_interval_ms"] == 58.0
  assert controller._last_long_tx_echo["echo_matches_last_attempt"] is True
  assert events[-1][0] == "tesla.das_control_returned"
