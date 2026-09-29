from openpilot.sunnypilot.selfdrive.car.tesla.validation_controller import (
  DAS_BODY_CONTROLS_ADDRESS,
  TeslaTurnSignalRealtimeController,
  VEHICLE_FEEDBACK_TIMEOUT_NS,
  create_body_control_frame,
  decode_body_controls,
  is_original_body_controls_frame,
  tesla_body_controls_checksum,
)
from openpilot.cereal import log
from openpilot.sunnypilot.navassist.lane_intent import (
  LaneIntentDirection, LaneTopologyInput, LaneVehicleInput, NavLaneIntentCoordinator,
  NavLanePlan, ObservedLaneChangeState,
)


def idle_body_controls(counter: int = 4) -> bytes:
  data = bytearray([0xA5, 0x8C, 0x61, 0xB4, 0x5A, 0xC3, (counter << 4) | 0x07, 0])
  data[7] = tesla_body_controls_checksum(data)
  return bytes(data)


def test_turn_frame_changes_only_owned_fields_and_recomputes_checksum():
  original = idle_body_controls()
  sent = create_body_control_frame(original, "left", 5)

  assert is_original_body_controls_frame(DAS_BODY_CONTROLS_ADDRESS, 1, original)
  assert decode_body_controls(sent)["turn_request"] == 1
  assert decode_body_controls(sent)["turn_request_reason"] == 8
  assert decode_body_controls(sent)["counter"] == 5
  assert sent[0] == original[0]
  assert sent[3:6] == original[3:6]
  assert sent[7] == tesla_body_controls_checksum(sent)


def test_disabled_controller_fails_closed_without_can_send():
  controller = TeslaTurnSignalRealtimeController(configured=False)
  assert not controller.submit_request("test", "left", 100)
  assert controller.take_can_sends(100) == []
  completed = controller.drain_completed()
  assert completed[0][0]["result"] == "BLOCKED"


def test_enabled_controller_requires_fresh_original_template():
  controller = TeslaTurnSignalRealtimeController(configured=True)
  assert controller.submit_request("test", "right", 100)
  assert controller.take_can_sends(100) == []

  original = idle_body_controls(9)
  controller.observe_frame(200, DAS_BODY_CONTROLS_ADDRESS, original, 1)
  sends = controller.take_can_sends(200)

  assert len(sends) == 1
  assert sends[0].address == DAS_BODY_CONTROLS_ADDRESS
  assert sends[0].src == 1
  assert decode_body_controls(sends[0].dat)["turn_request"] == 2
  assert decode_body_controls(sends[0].dat)["counter"] == 10


def test_rejected_action_retries_on_next_original_template():
  controller = TeslaTurnSignalRealtimeController(configured=True)
  started = 1_000_000_000
  assert controller.submit_request("test", "right", started, hold_until_cancel=True)

  controller.observe_frame(started, DAS_BODY_CONTROLS_ADDRESS, idle_body_controls(4), 1)
  first = controller.take_can_sends(started)[0]
  controller.observe_frame(started + 1, DAS_BODY_CONTROLS_ADDRESS, first.dat, 0xC1)

  assert controller.status()["cancel_requested"] is False
  assert controller.take_can_sends(started + 2) == []
  controller.observe_frame(started + 3, DAS_BODY_CONTROLS_ADDRESS, idle_body_controls(5), 1)
  retry = controller.take_can_sends(started + 3)[0]
  assert decode_body_controls(retry.dat)["turn_request"] == 2
  assert decode_body_controls(retry.dat)["counter"] == 6


def test_rejected_action_after_echo_does_not_cancel_active_request():
  controller = TeslaTurnSignalRealtimeController(configured=True)
  started = 1_000_000_000
  assert controller.submit_request("test", "left", started, hold_until_cancel=True)

  controller.observe_frame(started, DAS_BODY_CONTROLS_ADDRESS, idle_body_controls(4), 1)
  first = controller.take_can_sends(started)[0]
  controller.observe_frame(started + 1, DAS_BODY_CONTROLS_ADDRESS, first.dat, 0x81)
  controller.observe_frame(started + 2, DAS_BODY_CONTROLS_ADDRESS, idle_body_controls(5), 1)
  second = controller.take_can_sends(started + 2)[0]
  controller.observe_frame(started + 3, DAS_BODY_CONTROLS_ADDRESS, second.dat, 0xC1)

  assert controller.status()["cancel_requested"] is False
  controller.observe_frame(started + 4, DAS_BODY_CONTROLS_ADDRESS, idle_body_controls(6), 1)
  retry = controller.take_can_sends(started + 4)[0]
  assert decode_body_controls(retry.dat)["turn_request"] == 1


def test_repeated_action_rejections_finish_without_unneeded_cancel_at_feedback_timeout():
  controller = TeslaTurnSignalRealtimeController(configured=True)
  started = 1_000_000_000
  assert controller.submit_request("test", "right", started, hold_until_cancel=True)

  for index, counter in enumerate((4, 5, 6)):
    stamp = started + index * 10
    controller.observe_frame(stamp, DAS_BODY_CONTROLS_ADDRESS, idle_body_controls(counter), 1)
    sent = controller.take_can_sends(stamp)[0]
    controller.observe_frame(stamp + 1, DAS_BODY_CONTROLS_ADDRESS, sent.dat, 0xC1)
    assert controller.status()["cancel_requested"] is False

  controller.advance_time(started + VEHICLE_FEEDBACK_TIMEOUT_NS)
  assert controller.status() is None
  assert controller.drain_completed()[-1][0]["result"] == "CANCELLED_BEFORE_SEND"
  assert controller.submit_request("next", "left", started + VEHICLE_FEEDBACK_TIMEOUT_NS + 1)


def test_explicit_cancel_after_rejected_action_does_not_latch_cancel_failure():
  controller = TeslaTurnSignalRealtimeController(configured=True)
  started = 1_000_000_000
  assert controller.submit_request("test", "left", started, hold_until_cancel=True)
  controller.observe_frame(started, DAS_BODY_CONTROLS_ADDRESS, idle_body_controls(4), 1)
  action = controller.take_can_sends(started)[0]
  controller.observe_frame(started + 1, DAS_BODY_CONTROLS_ADDRESS, action.dat, 0xC1)

  assert controller.request_cancel("test", started + 2)
  assert controller.status() is None
  result = controller.drain_completed()[-1][0]
  assert result["result"] == "CANCELLED_BEFORE_SEND"
  assert result["action_rejections"] == result["action_frames_sent"] == 1
  assert controller.submit_request("next", "right", started + 3)


def test_pending_cancel_finishes_when_its_only_action_is_rejected():
  controller = TeslaTurnSignalRealtimeController(configured=True)
  started = 1_000_000_000
  assert controller.submit_request("test", "right", started, hold_until_cancel=True)
  controller.observe_frame(started, DAS_BODY_CONTROLS_ADDRESS, idle_body_controls(4), 1)
  action = controller.take_can_sends(started)[0]
  assert controller.request_cancel("test", started + 1)
  controller.observe_frame(started + 2, DAS_BODY_CONTROLS_ADDRESS, action.dat, 0xC1)

  assert controller.status() is None
  assert controller.drain_completed()[-1][0]["result"] == "CANCELLED_BEFORE_SEND"
  assert controller.submit_request("next", "left", started + 3)


def test_navigation_signal_session_waits_for_explicit_cancel_after_lane_change_cycle():
  controller = TeslaTurnSignalRealtimeController(configured=True)
  assert controller.submit_request("nav", "left", 100, hold_until_cancel=True)

  controller.update_lane_change_context(
    200, valid=True, state=int(log.LaneChangeState.laneChangeStarting),
    direction=int(log.LaneChangeDirection.left), lateral_active=True, brake_pressed=False,
  )
  controller.update_lane_change_context(
    300, valid=True, state=int(log.LaneChangeState.laneChangeFinishing),
    direction=int(log.LaneChangeDirection.left), lateral_active=True, brake_pressed=False,
  )
  controller.update_lane_change_context(
    400, valid=True, state=int(log.LaneChangeState.off),
    direction=int(log.LaneChangeDirection.none), lateral_active=True, brake_pressed=False,
  )

  assert controller.status() is not None
  assert not controller.status()["cancel_requested"]
  assert controller.request_cancel("nav", 500)
  assert controller.status() is None
  assert controller.drain_completed()[0][0]["result"] == "CANCELLED_BEFORE_SEND"


def test_app_red_light_keepalive_refreshes_only_the_matching_active_session_timeout():
  controller = TeslaTurnSignalRealtimeController(configured=True)
  started = 1_000_000_000
  assert controller.submit_request("nav", "left", started, hold_until_cancel=True)
  controller.observe_frame(started, DAS_BODY_CONTROLS_ADDRESS, idle_body_controls(4), 1)
  action = controller.take_can_sends(started)[0]
  controller.observe_frame(started + 1, DAS_BODY_CONTROLS_ADDRESS, action.dat, 0x81)
  controller.observe_frame(started + 2, 0x3F5, (1 << 50).to_bytes(8, "little"), 1)
  ui = bytearray(7)
  ui[3] = 2
  controller.observe_frame(started + 3, 0x311, bytes(ui), 0)
  assert not controller.refresh_session("other", started + 30_000_000_000)
  assert controller.refresh_session("nav", started + 30_000_000_000)

  controller.advance_time(started + 60_000_000_001)
  assert controller.status() is not None
  controller.advance_time(started + 90_000_000_001)
  assert controller.status()["cancel_requested"]


def test_navigation_lamp_follows_real_sp_starting_to_pre_cycle_until_coordinator_completes():
  coordinator = NavLaneIntentCoordinator()
  controller = TeslaTurnSignalRealtimeController(configured=True)
  plan = NavLanePlan(True, "session", 1, 7, 3, (0,), heuristic=True, edge_direction=LaneIntentDirection.left)
  topology = LaneTopologyInput(True, 3, 1, True, True, True, True)
  car = LaneVehicleInput(True, 15.0)
  for now_ns in (0, 500_000_000):
    coordinator.update(plan, topology, car, now_ns=now_ns)
  requested = coordinator.update(plan, topology, car, now_ns=1_000_000_000)
  assert requested.signal_requested
  assert controller.submit_request("nav", "left", 1_000_000_000, hold_until_cancel=True)
  controller.observe_frame(1_000_000_000, DAS_BODY_CONTROLS_ADDRESS, idle_body_controls(), 1)
  sent = controller.take_can_sends(1_000_000_000)
  assert len(sent) == 1

  for now_ns, state, expected_lamp in (
    (1_200_000_000, ObservedLaneChangeState.starting, True),
    (1_800_000_000, ObservedLaneChangeState.finishing, True),
    (2_200_000_000, ObservedLaneChangeState.finishing, True),
    (2_800_000_000, ObservedLaneChangeState.pre, False),
  ):
    car = LaneVehicleInput(True, 15.0, left_blinker=True, lane_change_state=state,
                           lane_change_direction=LaneIntentDirection.left)
    intent = coordinator.update(plan, topology, car, now_ns=now_ns)
    controller.update_lane_change_context(now_ns, valid=True, state=int(state), direction=int(LaneIntentDirection.left),
                                          lateral_active=True, brake_pressed=False)
    assert not controller.status()["cancel_requested"]
    assert intent.signal_requested == expected_lamp
  assert intent.reason == "laneChangeObserved"
  controller.request_cancel("nav", 2_800_000_000)
  assert controller.status()["cancel_requested"]


def test_manual_validation_still_cancels_at_real_sp_cycle_end():
  controller = TeslaTurnSignalRealtimeController(configured=True)
  assert controller.submit_request("manual-test", "left", 100)
  controller.observe_frame(200, DAS_BODY_CONTROLS_ADDRESS, idle_body_controls(), 1)
  assert controller.take_can_sends(200)
  for now_ns, state in ((300, log.LaneChangeState.laneChangeStarting), (400, log.LaneChangeState.preLaneChange)):
    controller.update_lane_change_context(now_ns, valid=True, state=int(state), direction=int(log.LaneChangeDirection.left),
                                          lateral_active=True, brake_pressed=False)
  assert controller.status()["cancel_reason"] == "lane_change_cycle_complete"
