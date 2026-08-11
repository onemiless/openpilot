import pytest

from cereal import log

from opendbc.car.tesla.turn_signal_controller import (
  TURN_SIGNAL_ADDRESS,
  TurnSignalController,
  body_controls_checksum,
  build_turn_frame,
  decode_body_controls,
)


def idle_body_controls(counter=3) -> bytes:
  data = bytearray([0x12, 0, 0x60, 0x81, 0x44, 0x25, counter << 4, 0])
  data[7] = body_controls_checksum(data)
  return bytes(data)


def test_build_turn_frame_clones_template_and_updates_protected_fields():
  template = idle_body_controls(6)
  action = build_turn_frame(template, "left")
  decoded = decode_body_controls(action)
  assert decoded == {"request": 1, "reason": 8, "counter": 7, "checksum": action[7]}
  assert action[0] == template[0]
  assert action[3:6] == template[3:6]
  assert body_controls_checksum(action) == action[7]


def test_turn_session_requires_matching_active_lane_change_context():
  controller = TurnSignalController(configured=True)
  assert controller.submit("test-left", "left", 0)
  controller.update_lane_change_context(
    1, valid=True, state=log.LaneChangeState.preLaneChange,
    direction=log.LaneChangeDirection.right, lateral_active=True, brake_pressed=False,
  )
  assert controller.take_can_sends(2) == []
  result = controller.drain_completed()
  assert result[0]["result"] == "CANCELLED_BEFORE_SEND"
  assert result[0]["requested_cancel_reason"] == "lane_change_direction_mismatch"


def test_turn_session_sends_action_then_cancel_from_fresh_templates():
  controller = TurnSignalController(configured=True)
  assert controller.submit("test-left", "left", 0)
  controller.update_lane_change_context(
    10, valid=True, state=log.LaneChangeState.preLaneChange,
    direction=log.LaneChangeDirection.left, lateral_active=True, brake_pressed=False,
  )
  template = idle_body_controls(4)
  controller.observe(20, TURN_SIGNAL_ADDRESS, template, 1)
  action = controller.take_can_sends(30)
  assert len(action) == 1
  assert decode_body_controls(action[0].dat)["request"] == 1

  controller.observe(40, TURN_SIGNAL_ADDRESS, action[0].dat, 0x81)
  controller.update_lane_change_context(
    50, valid=True, state=log.LaneChangeState.laneChangeStarting,
    direction=log.LaneChangeDirection.left, lateral_active=True, brake_pressed=False,
  )
  controller.update_lane_change_context(
    60, valid=True, state=log.LaneChangeState.laneChangeFinishing,
    direction=log.LaneChangeDirection.left, lateral_active=True, brake_pressed=False,
  )
  assert not controller.status()["cancel_requested"]
  assert controller.status()["phase"] == "lane_change_finishing"
  finishing_template = idle_body_controls(5)
  controller.observe(62, TURN_SIGNAL_ADDRESS, finishing_template, 1)
  finishing_action = controller.take_can_sends(63)
  assert len(finishing_action) == 1
  assert decode_body_controls(finishing_action[0].dat)["request"] == 1
  controller.observe(64, TURN_SIGNAL_ADDRESS, finishing_action[0].dat, 0x81)
  controller.update_lane_change_context(
    65, valid=True, state=log.LaneChangeState.off,
    direction=log.LaneChangeDirection.none, lateral_active=True, brake_pressed=False,
  )
  assert controller.status()["cancel_reason"] == "lane_change_complete"

  cancel_template = idle_body_controls(6)
  controller.observe(70, TURN_SIGNAL_ADDRESS, cancel_template, 1)
  cancel = controller.take_can_sends(80, cancel_only=True)
  assert len(cancel) == 1
  assert decode_body_controls(cancel[0].dat)["request"] == 3
  assert decode_body_controls(cancel[0].dat)["reason"] == 4


def test_turn_controller_is_disabled_by_default():
  controller = TurnSignalController(configured=False)
  assert not controller.submit("blocked", "right", 0)
  assert controller.drain_completed()[0]["result"] == "BLOCKED"


def test_automatic_lane_change_starts_without_web_request_and_cancels_only_after_completion():
  controller = TurnSignalController(configured=False, auto_configured=True)
  template = idle_body_controls(4)
  controller.observe(10, TURN_SIGNAL_ADDRESS, template, 1)
  controller.update_lane_change_context(
    20, valid=True, state=log.LaneChangeState.preLaneChange,
    direction=log.LaneChangeDirection.left, lateral_active=True, brake_pressed=False,
    vehicle_left_blinker=False, vehicle_right_blinker=False,
    automatic_direction="left",
  )

  action = controller.take_can_sends(30)
  assert len(action) == 1
  assert decode_body_controls(action[0].dat)["request"] == 1
  assert controller.status()["origin"] == "automatic_lane_change"

  controller.observe(40, TURN_SIGNAL_ADDRESS, action[0].dat, 0x81)
  controller.update_lane_change_context(
    50, valid=True, state=log.LaneChangeState.laneChangeStarting,
    direction=log.LaneChangeDirection.left, lateral_active=True, brake_pressed=False,
    vehicle_left_blinker=True, vehicle_right_blinker=False,
  )
  controller.update_lane_change_context(
    60, valid=True, state=log.LaneChangeState.laneChangeFinishing,
    direction=log.LaneChangeDirection.left, lateral_active=True, brake_pressed=False,
    vehicle_left_blinker=True, vehicle_right_blinker=False,
  )
  assert not controller.status()["cancel_requested"]

  controller.update_lane_change_context(
    70, valid=True, state=log.LaneChangeState.off,
    direction=log.LaneChangeDirection.none, lateral_active=True, brake_pressed=False,
    vehicle_left_blinker=True, vehicle_right_blinker=False,
  )
  assert controller.status()["cancel_reason"] == "lane_change_complete"


@pytest.mark.parametrize("vehicle_left_blinker,vehicle_right_blinker", [(False, True), (True, False)])
def test_automatic_lane_change_does_not_override_any_driver_blinker(vehicle_left_blinker, vehicle_right_blinker):
  controller = TurnSignalController(configured=False, auto_configured=True)
  controller.observe(10, TURN_SIGNAL_ADDRESS, idle_body_controls(4), 1)
  controller.update_lane_change_context(
    20, valid=True, state=log.LaneChangeState.preLaneChange,
    direction=log.LaneChangeDirection.right, lateral_active=True, brake_pressed=False,
    vehicle_left_blinker=vehicle_left_blinker, vehicle_right_blinker=vehicle_right_blinker,
    automatic_direction="right",
  )
  assert controller.status() is None
  assert controller.take_can_sends(30) == []


def test_lane_change_state_without_automatic_intent_does_not_start_turn_signal():
  controller = TurnSignalController(configured=False, auto_configured=True)
  controller.observe(10, TURN_SIGNAL_ADDRESS, idle_body_controls(4), 1)
  controller.update_lane_change_context(
    20, valid=True, state=log.LaneChangeState.preLaneChange,
    direction=log.LaneChangeDirection.left, lateral_active=True, brake_pressed=False,
    vehicle_left_blinker=False, vehicle_right_blinker=False, automatic_direction="none",
  )
  assert controller.status() is None
  assert controller.take_can_sends(30) == []
