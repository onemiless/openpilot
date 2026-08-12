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
  (110.3, -0.1),
  (110.3, 0.1),
  (124.6, -0.1),
  (124.6, 0.1),
))
def test_active_longitudinal_set_speed_stays_near_vehicle_speed(speed_kph, accel):
  tesla_can = TeslaCAN(CANPacker("tesla_model3_party"))

  message = tesla_can.create_longitudinal_command(4, accel, 1, speed_kph / 3.6, True)
  signals = decode_das_control(message)

  expected_set_speed = min(max(speed_kph / 3.6 + accel, 0) * 3.6, 400)
  assert signals["DAS_setSpeed"] == pytest.approx(expected_set_speed, abs=0.11)


def test_active_longitudinal_jerk_max_ramps_from_zero_at_sp_rate():
  tesla_can = TeslaCAN(CANPacker("tesla_model3_party"))

  first = decode_das_control(tesla_can.create_longitudinal_command(4, 0.0, 1, 20.0, True))
  assert first["DAS_jerkMin"] == pytest.approx(-4.9, abs=0.02)
  assert first["DAS_jerkMax"] == pytest.approx(0.04, abs=0.02)

  # At 25 Hz and 1.0 m/s^3/s, the requested maximum reaches 4.9 in 123 frames.
  for counter in range(2, 124):
    message = tesla_can.create_longitudinal_command(4, 0.0, counter % 8, 20.0, True)
  saturated = decode_das_control(message)
  assert saturated["DAS_jerkMax"] == pytest.approx(4.9, abs=0.02)
  assert tesla_can.jerk == pytest.approx(4.9)


def test_controller_resets_jerk_ramp_for_each_new_ownership_session():
  controller, cc, cs, _, now_nanos = controller_fixture()

  first = controller.update_longitudinal_control(cc, cs, cruise_cancel=False, now_nanos=now_nanos)[0]
  assert decode_das_control(first)["DAS_jerkMax"] == pytest.approx(0.04, abs=0.02)
  assert controller._last_long_tx["ownership_age_ms"] == 0.0
  assert controller._last_long_tx["jerk_ramp_age_ms"] == 0.0
  assert controller._last_long_tx["jerk_reset_reason"] == "ownership_acquired"

  controller.frame += 4
  now_nanos += 40_000_000
  second = controller.update_longitudinal_control(cc, cs, cruise_cancel=False, now_nanos=now_nanos)[0]
  assert decode_das_control(second)["DAS_jerkMax"] == pytest.approx(0.08, abs=0.02)
  assert controller._last_long_tx["ownership_age_ms"] == 40.0
  assert controller._last_long_tx["jerk_ramp_age_ms"] == 40.0

  controller.frame += 4
  now_nanos += 40_000_000
  cc.longActive = False
  controller.update_longitudinal_control(cc, cs, cruise_cancel=False, now_nanos=now_nanos)
  controller.frame += 4
  now_nanos += 40_000_000
  controller.update_longitudinal_control(cc, cs, cruise_cancel=False, now_nanos=now_nanos)

  now_nanos += 400_000_001
  cs.das_control_nanos = now_nanos
  controller.frame += 4
  cc.longActive = True
  reacquired = controller.update_longitudinal_control(cc, cs, cruise_cancel=False, now_nanos=now_nanos)[0]
  assert decode_das_control(reacquired)["DAS_jerkMax"] == pytest.approx(0.04, abs=0.02)
  assert controller._last_long_tx["jerk_reset_reason"] == "ownership_acquired"


def test_controller_records_complete_packed_longitudinal_payload_and_interval():
  controller, cc, cs, _, now_nanos = controller_fixture()

  first = controller.update_longitudinal_control(cc, cs, cruise_cancel=False, now_nanos=now_nanos)[0]
  assert controller._last_long_tx["tx_raw"] == first[1].hex()
  assert controller._last_long_tx["tx_set_speed_kph"] == 75.6
  assert controller._last_long_tx["tx_accel_min"] == 1.0
  assert controller._last_long_tx["tx_counter"] == 4
  assert controller._last_long_tx["tx_checksum_valid"] is True
  assert controller._last_long_tx["tx_interval_ms"] is None

  controller.frame += 4
  now_nanos += 40_000_000
  second = controller.update_longitudinal_control(cc, cs, cruise_cancel=False, now_nanos=now_nanos)[0]
  assert controller._last_long_tx["tx_raw"] == second[1].hex()
  assert controller._last_long_tx["tx_counter"] == 5
  assert controller._last_long_tx["tx_interval_ms"] == 40.0


def test_longitudinal_ownership_is_silent_at_startup_and_releases_after_cancel():
  ownership = TeslaLongitudinalOwnership()

  assert ownership.update(long_active=False, cancel=False) == LongitudinalAction.NONE

  assert ownership.update(long_active=True, cancel=False) == LongitudinalAction.CONTROL
  assert ownership.update(long_active=False, cancel=False) == LongitudinalAction.CANCEL
  assert ownership.update(long_active=False, cancel=False) == LongitudinalAction.RELEASE
  assert ownership.update(long_active=False, cancel=False) == LongitudinalAction.NONE


def test_controller_stops_acc_on_after_cancel_and_releases_oem_ownership():
  controller, cc, cs, das_control, now_nanos = controller_fixture(long_active=False)

  assert controller.update_longitudinal_control(cc, cs, cruise_cancel=False, now_nanos=now_nanos) == []

  controller.frame += 4
  cc.longActive = True
  control = controller.update_longitudinal_control(cc, cs, cruise_cancel=False, now_nanos=now_nanos)
  assert control[0][1][1] >> 4 == 4
  assert control[0][1][6] >> 5 == 4

  das_control["DAS_controlCounter"] = 4
  controller.frame += 4
  control = controller.update_longitudinal_control(cc, cs, cruise_cancel=False, now_nanos=now_nanos)
  assert control[0][1][6] >> 5 == 5

  das_control["DAS_controlCounter"] = 5
  controller.frame += 4
  cc.longActive = False
  cancel = controller.update_longitudinal_control(cc, cs, cruise_cancel=False, now_nanos=now_nanos)
  assert cancel[0][1][1] >> 4 == 13
  assert cancel[0][1][2] & 0x03 == 0
  assert cancel[0][1][6] >> 5 == 6

  das_control["DAS_controlCounter"] = 6
  controller.frame += 4
  release = controller.update_longitudinal_control(cc, cs, cruise_cancel=False, now_nanos=now_nanos)
  release_signals = decode_das_control(release[0])
  assert release_signals["DAS_aebEvent"] == TESLA_LONGITUDINAL_HANDOFF_AEB_EVENT
  assert release_signals["DAS_controlCounter"] == 6
  assert release[0][1][7] == TeslaCAN.checksum(0x2B9, release[0][1][:7])

  controller.frame += 4
  assert controller.update_longitudinal_control(cc, cs, cruise_cancel=False, now_nanos=now_nanos) == []

  # Do not race Panda's RX-side handoff completion with an immediate reacquire.
  cc.longActive = True
  controller.frame += 4
  assert controller.update_longitudinal_control(cc, cs, cruise_cancel=False, now_nanos=now_nanos) == []

  # After one full OEM counter cycle, reacquisition resyncs to the latest OEM
  # counter instead of continuing CP's previous sequence.
  now_nanos += 400_000_001
  cs.das_control_nanos = now_nanos
  das_control["DAS_controlCounter"] = 7
  controller.frame += 4
  reacquire = controller.update_longitudinal_control(cc, cs, cruise_cancel=False, now_nanos=now_nanos)
  assert reacquire[0][1][1] >> 4 == 4
  assert reacquire[0][1][6] >> 5 == 0


def test_controller_requires_fresh_oem_state_and_releases_on_brake():
  controller, cc, cs, _, now_nanos = controller_fixture(counter=2, fresh=False)

  # No fresh OEM counter means no takeover and no synthetic startup marker.
  assert controller.update_longitudinal_control(cc, cs, cruise_cancel=False, now_nanos=now_nanos) == []
  controller.frame += 4
  assert controller.update_longitudinal_control(cc, cs, cruise_cancel=False, now_nanos=now_nanos) == []

  # A fresh OEM state permits takeover and synchronizes its counter.
  cs.das_control_nanos = now_nanos
  controller.frame += 4
  control = controller.update_longitudinal_control(cc, cs, cruise_cancel=False, now_nanos=now_nanos)
  assert control[0][1][1] >> 4 == 4
  assert control[0][1][6] >> 5 == 3

  # OEM freshness gates takeover only. A short OEM input gap must not create
  # an unrequested source handoff while CP already owns DAS_control.
  cs.das_control_nanos = 1
  controller.frame += 4
  control = controller.update_longitudinal_control(cc, cs, cruise_cancel=False, now_nanos=now_nanos)
  assert len(control) == 1
  assert decode_das_control(control[0])["DAS_accState"] == 4

  # Brake is an independent fail-closed guard even if CC.longActive is stale.
  cs.out.brakePressed = True
  controller.frame += 4
  cancel = controller.update_longitudinal_control(cc, cs, cruise_cancel=False, now_nanos=now_nanos)
  assert len(cancel) == 1
  assert cancel[0][1][1] >> 4 == 13


def test_controller_handoff_uses_last_cp_counter_when_oem_counter_drifts():
  controller, cc, cs, das_control, now_nanos = controller_fixture()

  control = controller.update_longitudinal_control(cc, cs, cruise_cancel=False, now_nanos=now_nanos)
  assert decode_das_control(control[0])["DAS_controlCounter"] == 4

  controller.frame += 4
  cc.longActive = False
  cancel = controller.update_longitudinal_control(cc, cs, cruise_cancel=False, now_nanos=now_nanos)
  cancel_counter = decode_das_control(cancel[0])["DAS_controlCounter"]

  # The marker carries the last CP counter rather than a racing OEM snapshot.
  # Panda then waits for exactly counter+1 before forwarding OEM again.
  das_control["DAS_controlCounter"] = (cancel_counter + 2) % 8
  controller.frame += 4
  handoff = controller.update_longitudinal_control(cc, cs, cruise_cancel=False, now_nanos=now_nanos)
  assert decode_das_control(handoff[0])["DAS_controlCounter"] == cancel_counter
  assert decode_das_control(handoff[0])["DAS_aebEvent"] == TESLA_LONGITUDINAL_HANDOFF_AEB_EVENT

  cc.longActive = True
  controller.frame += 4
  assert controller.update_longitudinal_control(cc, cs, cruise_cancel=False, now_nanos=now_nanos) == []
