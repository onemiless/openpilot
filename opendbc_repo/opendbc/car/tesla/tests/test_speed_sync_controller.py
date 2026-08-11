from types import SimpleNamespace

import pytest

from opendbc.car.tesla.speed_sync_controller import (
  MANUAL_RESUME_GESTURE_NS,
  SPEED_BUTTON_ADDRESS,
  SpeedSyncController,
  build_speed_tick,
  signed_wheel_tick,
)


def idle_speed_button() -> bytes:
  return bytes([1, 0x21, 0x42, 0, 0x84, 0xA5, 0xC6, 0xE7])


def make_context(speed_kph=70.0):
  cc = SimpleNamespace(enabled=True, longActive=True, cruiseControl=SimpleNamespace(cancel=False))
  out = SimpleNamespace(
    cruiseState=SimpleNamespace(speed=speed_kph / 3.6, enabled=True),
    brakePressed=False,
  )
  cs = SimpleNamespace(out=out, tesla_speed_units="KPH", tesla_autopilot_active=False)
  return cc, cs


def test_speed_tick_changes_only_right_wheel_bits():
  template = idle_speed_button()
  up = build_speed_tick(template, 1)
  down = build_speed_tick(template, -1)
  assert signed_wheel_tick(up) == 1
  assert signed_wheel_tick(down) == -1
  assert up[:3] == template[:3] and up[4:] == template[4:]
  assert down[:3] == template[:3] and down[4:] == template[4:]
  with pytest.raises(ValueError):
    build_speed_tick(template, 2)


def test_speed_sync_stabilizes_waits_for_feedback_and_steps_again():
  controller = SpeedSyncController(configured=True)
  cc, cs = make_context(70)
  controller.observe(0, SPEED_BUTTON_ADDRESS, idle_speed_button(), 1)

  assert controller.update(cc, cs, 72 / 3.6, True, 0) == []
  sends = controller.update(cc, cs, 72 / 3.6, True, 500_000_000)
  assert len(sends) == 1
  assert signed_wheel_tick(sends[0].dat) == 1

  assert controller.update(cc, cs, 72 / 3.6, True, 700_000_000) == []
  cs.out.cruiseState.speed = 71 / 3.6
  controller.observe(800_000_000, SPEED_BUTTON_ADDRESS, idle_speed_button(), 1)
  assert controller.update(cc, cs, 72 / 3.6, True, 800_000_000) == []
  sends = controller.update(cc, cs, 72 / 3.6, True, 1_000_000_000)
  assert len(sends) == 1
  assert signed_wheel_tick(sends[0].dat) == 1


def test_carrot_target_is_synced_into_tesla_host_until_feedback_reaches_target():
  controller = SpeedSyncController(configured=True)
  cc, cs = make_context(40)
  target_mps = 90 / 3.6
  controller.observe(0, SPEED_BUTTON_ADDRESS, idle_speed_button(), 1)

  assert controller.update(cc, cs, target_mps, True, 0) == []
  sends = controller.update(cc, cs, target_mps, True, 500_000_000)
  assert len(sends) == 1
  assert signed_wheel_tick(sends[0].dat) == 1

  # Each Tesla host feedback step unlocks the next +1 tick. The controller must
  # keep synchronizing the physical set speed instead of stopping at CP's target.
  for speed_kph in range(41, 90):
    now_nanos = (speed_kph - 39) * 500_000_000
    cs.out.cruiseState.speed = speed_kph / 3.6
    controller.observe(now_nanos, SPEED_BUTTON_ADDRESS, idle_speed_button(), 1)
    sends = controller.update(cc, cs, target_mps, True, now_nanos)
    assert len(sends) == 1
    assert signed_wheel_tick(sends[0].dat) == 1

  now_nanos = 25_500_000_000
  cs.out.cruiseState.speed = 90 / 3.6
  controller.observe(now_nanos, SPEED_BUTTON_ADDRESS, idle_speed_button(), 1)
  assert controller.update(cc, cs, target_mps, True, now_nanos) == []
  assert controller.status()["state"] == "synced"


def test_manual_adjustment_pauses_and_opposite_gesture_resumes_within_one_second():
  controller = SpeedSyncController(configured=True)
  cc, cs = make_context(70)
  controller.observe(0, SPEED_BUTTON_ADDRESS, idle_speed_button(), 1)

  manual_up = build_speed_tick(idle_speed_button(), 1)
  manual_down = build_speed_tick(idle_speed_button(), -1)
  controller.observe(2_000_000_000, SPEED_BUTTON_ADDRESS, manual_up, 1)
  assert controller.update(cc, cs, 72 / 3.6, True, 2_000_000_000) == []
  assert controller.status()["reason"] == "manual_override"

  controller.observe(2_000_000_000 + MANUAL_RESUME_GESTURE_NS, SPEED_BUTTON_ADDRESS, manual_down, 1)
  assert controller.update(cc, cs, 72 / 3.6, True, 3_000_000_000) == []
  assert controller.manual_override is False
  assert controller.status()["state"] == "stabilizing"


def test_manual_opposite_gesture_after_one_second_stays_paused():
  controller = SpeedSyncController(configured=True)
  cc, cs = make_context(70)
  controller.observe(2_000_000_000, SPEED_BUTTON_ADDRESS, build_speed_tick(idle_speed_button(), 1), 1)
  controller.update(cc, cs, 72 / 3.6, True, 2_000_000_000)
  controller.observe(3_000_000_001, SPEED_BUTTON_ADDRESS, build_speed_tick(idle_speed_button(), -1), 1)
  controller.update(cc, cs, 72 / 3.6, True, 3_000_000_001)
  assert controller.manual_override is True
  assert controller.status()["reason"] == "manual_override"


def test_manual_override_clears_when_longitudinal_control_reengages():
  controller = SpeedSyncController(configured=True)
  cc, cs = make_context(70)
  controller.observe(2_000_000_000, SPEED_BUTTON_ADDRESS, build_speed_tick(idle_speed_button(), 1), 1)
  controller.update(cc, cs, 72 / 3.6, True, 2_000_000_000)
  assert controller.manual_override is True

  cc.longActive = False
  controller.update(cc, cs, 72 / 3.6, True, 2_100_000_000)
  assert controller.manual_override is False

  cc.longActive = True
  controller.update(cc, cs, 72 / 3.6, True, 2_200_000_000)
  assert controller.status()["state"] == "stabilizing"


def test_speed_limit_change_clears_manual_override():
  controller = SpeedSyncController(configured=True)
  cc, cs = make_context(70)
  controller.observe(2_000_000_000, SPEED_BUTTON_ADDRESS, build_speed_tick(idle_speed_button(), 1), 1)
  controller.update(cc, cs, 72 / 3.6, True, 2_000_000_000)
  assert controller.manual_override is True

  controller.update(cc, cs, 75 / 3.6, True, 2_100_000_000)
  assert controller.manual_override is False
  assert controller.status()["state"] == "stabilizing"


def test_external_cruise_speed_change_pauses_automatic_sync():
  controller = SpeedSyncController(configured=True)
  cc, cs = make_context(70)
  controller.observe(0, SPEED_BUTTON_ADDRESS, idle_speed_button(), 1)
  controller.update(cc, cs, 70 / 3.6, True, 0)
  controller.update(cc, cs, 70 / 3.6, True, 500_000_000)
  assert controller.status()["state"] == "synced"

  cs.out.cruiseState.speed = 72 / 3.6
  controller.observe(600_000_000, SPEED_BUTTON_ADDRESS, idle_speed_button(), 1)
  assert controller.update(cc, cs, 70 / 3.6, True, 600_000_000) == []
  assert controller.manual_override is True
  assert controller.status()["reason"] == "manual_override"


@pytest.mark.parametrize("change,reason", [
  ({"longActive": False}, "longitudinal_inactive"),
  ({"ap": True}, "tesla_ap_active"),
  ({"brake": True}, "brake_pressed"),
])
def test_speed_sync_fails_closed(change, reason):
  controller = SpeedSyncController(configured=True)
  cc, cs = make_context(70)
  if "longActive" in change:
    cc.longActive = change["longActive"]
  if "ap" in change:
    cs.tesla_autopilot_active = change["ap"]
  if "brake" in change:
    cs.out.brakePressed = change["brake"]
  assert controller.update(cc, cs, 72 / 3.6, True, 0) == []
  assert controller.status()["reason"] == reason
