from cereal import log
from opendbc.can.packer import CANPacker

from openpilot.selfdrive.car.tesla_turn_signal_controller import (
  REQUEST_PARAM,
  RESULT_PARAM,
  TeslaTurnSignalRealtimeController,
  create_body_control_frame,
  tesla_body_controls_checksum,
)
from openpilot.selfdrive.debug.tesla_turn_signal_test import send_validation_pulse


OBSERVED_BODY_CONTROLS = bytes.fromhex("008802000000b026")


def idle_body_controls(counter: int) -> bytes:
  data = bytearray(OBSERVED_BODY_CONTROLS)
  data[1] &= 0xFC
  data[6] = (data[6] & 0x0F) | ((counter & 0xF) << 4)
  data[7] = tesla_body_controls_checksum(data)
  return bytes(data)


def test_realtime_controller_sends_until_sp_finishing_then_cancels():
  controller = TeslaTurnSignalRealtimeController(configured=True)
  controller.submit_request("left-session", "left", 1_000_000_000)
  controller.update_lane_change_context(1_010_000_000, valid=True, state=log.LaneChangeState.off,
                                        direction=log.LaneChangeDirection.none, lateral_active=True,
                                        brake_pressed=False)

  action_frame_count = 8
  for index in range(action_frame_count):
    now = 1_100_000_000 + index * 100_000_000
    template = idle_body_controls(4 + index)
    controller.observe_frame(now, 0x3E9, template, 1)
    sends = controller.take_can_sends(now + 1_000_000)
    assert len(sends) == 1
    assert sends[0].dat == create_body_control_frame(template, "left", 5 + index)
    controller.observe_frame(now + 2_000_000, 0x3E9, sends[0].dat, 0x81)

  packer = CANPacker("tesla_model3_party")
  ui_warning = packer.make_can_msg("UI_warning", 0, {"leftBlinkerBlinking": 2, "rightBlinkerBlinking": 0})
  controller.observe_frame(1_650_000_000, ui_warning[0], ui_warning[1], 0)
  controller.update_lane_change_context(1_660_000_000, valid=True, state=log.LaneChangeState.preLaneChange,
                                        direction=log.LaneChangeDirection.left, lateral_active=True,
                                        brake_pressed=False)
  controller.update_lane_change_context(1_670_000_000, valid=True, state=log.LaneChangeState.laneChangeStarting,
                                        direction=log.LaneChangeDirection.left, lateral_active=True,
                                        brake_pressed=False)
  controller.update_lane_change_context(1_680_000_000, valid=True, state=log.LaneChangeState.laneChangeFinishing,
                                        direction=log.LaneChangeDirection.left, lateral_active=True,
                                        brake_pressed=False)

  cancel_template = idle_body_controls(13)
  controller.observe_frame(1_700_000_000, 0x3E9, cancel_template, 1)
  cancel = controller.take_can_sends(1_701_000_000)
  assert len(cancel) == 1
  assert cancel[0].dat == create_body_control_frame(cancel_template, "cancel", 14)
  controller.observe_frame(1_702_000_000, 0x3E9, cancel[0].dat, 0x81)

  lighting_packer = CANPacker("tesla_model3_vehicle")
  lighting_off = lighting_packer.make_can_msg("ID3F5VCFRONT_lighting", 1, {
    "VCFRONT_turnSignalLeftStatus": 0,
    "VCFRONT_turnSignalRightStatus": 0,
  })
  controller.observe_frame(1_710_000_000, lighting_off[0], lighting_off[1], 1)

  completed = controller.drain_completed()
  assert len(completed) == 1
  result, records = completed[0]
  assert result == {
    "test_id": "left-session",
    "direction": "left",
    "result": "PASS",
    "feedback": True,
    "tx_echo": True,
    "rejected": False,
    "action_frames_sent": action_frame_count,
    "cancel_sent": True,
    "cancel_attempts": 1,
    "cancel_reason": "lane_change_finishing",
    "lane_change_started": True,
  }
  assert [record["event"] for record in records].count("frame_submitted") == action_frame_count + 1


def test_realtime_controller_requires_a_new_oem_template_for_each_send():
  controller = TeslaTurnSignalRealtimeController(configured=True)
  controller.submit_request("right-session", "right", 1_000_000_000)
  template = idle_body_controls(4)
  controller.observe_frame(1_100_000_000, 0x3E9, template, 1)

  first = controller.take_can_sends(1_101_000_000)
  assert len(first) == 1
  controller.observe_frame(1_102_000_000, 0x3E9, first[0].dat, 0x81)
  assert controller.take_can_sends(1_103_000_000) == []


def test_realtime_controller_brake_requests_cancel():
  controller = TeslaTurnSignalRealtimeController(configured=True)
  controller.submit_request("brake-session", "right", 1_000_000_000)
  template = idle_body_controls(4)
  controller.observe_frame(1_005_000_000, 0x3E9, template, 1)
  action = controller.take_can_sends(1_006_000_000)[0]
  controller.observe_frame(1_007_000_000, 0x3E9, action.dat, 0x81)
  controller.update_lane_change_context(1_010_000_000, valid=True, state=log.LaneChangeState.preLaneChange,
                                        direction=log.LaneChangeDirection.right, lateral_active=True,
                                        brake_pressed=True)
  status = controller.status()
  assert status is not None
  assert status["phase"] == "cancelling"
  assert status["cancel_reason"] == "brake_pressed"


def test_realtime_controller_stale_context_requests_cancel_after_grace():
  controller = TeslaTurnSignalRealtimeController(configured=True)
  controller.submit_request("stale-session", "left", 1_000_000_000)
  template = idle_body_controls(4)
  controller.observe_frame(1_005_000_000, 0x3E9, template, 1)
  action = controller.take_can_sends(1_006_000_000)[0]
  controller.observe_frame(1_007_000_000, 0x3E9, action.dat, 0x81)
  controller.update_lane_change_context(2_000_000_001, valid=False, state=log.LaneChangeState.off,
                                        direction=log.LaneChangeDirection.none, lateral_active=True,
                                        brake_pressed=False)
  status = controller.status()
  assert status is not None
  assert status["cancel_reason"] == "lane_change_context_stale"


def test_realtime_controller_cancel_before_first_action_sends_no_can():
  controller = TeslaTurnSignalRealtimeController(configured=True)
  controller.submit_request("early-cancel", "left", 1_000_000_000)
  assert controller.request_cancel("early-cancel", 1_010_000_000)
  template = idle_body_controls(4)
  controller.observe_frame(1_020_000_000, 0x3E9, template, 1)
  assert controller.take_can_sends(1_021_000_000) == []
  result, _ = controller.drain_completed()[0]
  assert result["result"] == "CANCELLED_BEFORE_SEND"
  assert result["requested_cancel_reason"] == "web_cancel"


def test_realtime_controller_action_echo_timeout_attempts_cancel():
  controller = TeslaTurnSignalRealtimeController(configured=True)
  controller.submit_request("echo-timeout", "right", 1_000_000_000)
  first_template = idle_body_controls(4)
  controller.observe_frame(1_010_000_000, 0x3E9, first_template, 1)
  assert len(controller.take_can_sends(1_011_000_000)) == 1

  controller.advance_time(2_211_000_001)
  status = controller.status()
  assert status is not None
  assert status["cancel_reason"] == "action_tx_echo_timeout"

  cancel_template = idle_body_controls(5)
  controller.observe_frame(2_220_000_000, 0x3E9, cancel_template, 1)
  cancel = controller.take_can_sends(2_221_000_000)
  assert len(cancel) == 1
  assert cancel[0].dat == create_body_control_frame(cancel_template, "cancel", 6)


def test_realtime_controller_feedback_timeout_attempts_cancel():
  controller = TeslaTurnSignalRealtimeController(configured=True)
  controller.submit_request("feedback-timeout", "left", 1_000_000_000)
  template = idle_body_controls(4)
  controller.observe_frame(1_010_000_000, 0x3E9, template, 1)
  action = controller.take_can_sends(1_011_000_000)[0]
  controller.observe_frame(1_012_000_000, 0x3E9, action.dat, 0x81)

  controller.advance_time(3_500_000_001)
  status = controller.status()
  assert status is not None
  assert status["cancel_reason"] == "vehicle_feedback_timeout"


def test_realtime_controller_rejected_later_action_attempts_cancel():
  controller = TeslaTurnSignalRealtimeController(configured=True)
  controller.submit_request("late-rejection", "right", 1_000_000_000)
  first_template = idle_body_controls(4)
  controller.observe_frame(1_010_000_000, 0x3E9, first_template, 1)
  first_action = controller.take_can_sends(1_011_000_000)[0]
  controller.observe_frame(1_012_000_000, 0x3E9, first_action.dat, 0x81)

  second_template = idle_body_controls(5)
  controller.observe_frame(1_020_000_000, 0x3E9, second_template, 1)
  second_action = controller.take_can_sends(1_021_000_000)[0]
  controller.observe_frame(1_022_000_000, 0x3E9, second_action.dat, 0xC1)
  status = controller.status()
  assert status is not None
  assert status["cancel_reason"] == "action_panda_rejected"

  cancel_template = idle_body_controls(6)
  controller.observe_frame(1_030_000_000, 0x3E9, cancel_template, 1)
  cancel = controller.take_can_sends(1_031_000_000)
  assert len(cancel) == 1
  assert cancel[0].dat == create_body_control_frame(cancel_template, "cancel", 7)


def test_realtime_controller_cancel_without_new_template_finishes_bounded():
  controller = TeslaTurnSignalRealtimeController(configured=True)
  controller.submit_request("no-cancel-template", "left", 1_000_000_000)
  template = idle_body_controls(4)
  controller.observe_frame(1_010_000_000, 0x3E9, template, 1)
  action = controller.take_can_sends(1_011_000_000)[0]
  controller.observe_frame(1_012_000_000, 0x3E9, action.dat, 0x81)
  assert controller.request_cancel("no-cancel-template", 1_020_000_000)

  controller.advance_time(2_520_000_001)
  result, _ = controller.drain_completed()[0]
  assert result["result"] == "CANCEL_NOT_SENT"


def test_realtime_controller_cancel_only_path_never_sends_action():
  controller = TeslaTurnSignalRealtimeController(configured=True)
  controller.submit_request("failsafe-path", "right", 1_000_000_000)
  first_template = idle_body_controls(4)
  controller.observe_frame(1_010_000_000, 0x3E9, first_template, 1)
  assert controller.take_can_sends(1_011_000_000, cancel_only=True) == []

  action = controller.take_can_sends(1_012_000_000)[0]
  controller.observe_frame(1_013_000_000, 0x3E9, action.dat, 0x81)
  assert controller.request_cancel("failsafe-path", 1_020_000_000)
  cancel_template = idle_body_controls(5)
  controller.observe_frame(1_030_000_000, 0x3E9, cancel_template, 1)
  cancel = controller.take_can_sends(1_031_000_000, cancel_only=True)
  assert len(cancel) == 1
  assert cancel[0].dat == create_body_control_frame(cancel_template, "cancel", 6)


def test_realtime_controller_retries_cancel_after_echo_timeout_and_confirms_lights_off():
  controller = TeslaTurnSignalRealtimeController(configured=True)
  controller.submit_request("cancel-retry", "left", 1_000_000_000)
  action_template = idle_body_controls(4)
  controller.observe_frame(1_010_000_000, 0x3E9, action_template, 1)
  action = controller.take_can_sends(1_011_000_000)[0]
  controller.observe_frame(1_012_000_000, 0x3E9, action.dat, 0x81)

  packer = CANPacker("tesla_model3_party")
  ui_warning = packer.make_can_msg("UI_warning", 0, {"leftBlinkerBlinking": 2, "rightBlinkerBlinking": 0})
  controller.observe_frame(1_020_000_000, ui_warning[0], ui_warning[1], 0)
  assert controller.request_cancel("cancel-retry", 1_030_000_000)

  first_cancel_template = idle_body_controls(5)
  controller.observe_frame(1_040_000_000, 0x3E9, first_cancel_template, 1)
  first_cancel = controller.take_can_sends(1_041_000_000)
  assert len(first_cancel) == 1

  controller.advance_time(2_241_000_001)
  retry_template = idle_body_controls(6)
  controller.observe_frame(2_250_000_000, 0x3E9, retry_template, 1)
  retry = controller.take_can_sends(2_251_000_000)
  assert len(retry) == 1
  assert retry[0].dat == create_body_control_frame(retry_template, "cancel", 7)
  assert controller.status()["cancel_attempts"] == 2

  # Safety rejects a duplicate cancel if the first cancel was accepted but its
  # host-side echo was lost. The controller then verifies the physical light.
  controller.observe_frame(2_252_000_000, 0x3E9, retry[0].dat, 0xC1)
  lighting_packer = CANPacker("tesla_model3_vehicle")
  lighting_off = lighting_packer.make_can_msg("ID3F5VCFRONT_lighting", 1, {
    "VCFRONT_turnSignalLeftStatus": 0,
    "VCFRONT_turnSignalRightStatus": 0,
  })
  controller.observe_frame(2_260_000_000, lighting_off[0], lighting_off[1], 1)
  result, _ = controller.drain_completed()[0]
  assert result["result"] == "PASS"
  assert result["cancel_attempts"] == 2


class FakeParams:
  def __init__(self):
    self.request = None

  def get_bool(self, key):
    return True

  def put(self, key, value, block=False):
    self.request = value

  def get(self, key):
    if key != RESULT_PARAM or self.request is None:
      return None
    return {
      "test_id": self.request["test_id"],
      "direction": self.request["direction"],
      "result": "PASS",
      "feedback": True,
      "tx_echo": True,
      "rejected": False,
      "action_frames_sent": 8,
      "cancel_sent": True,
      "cancel_reason": "lane_change_finishing",
      "lane_change_started": True,
    }


class FakeControllerParams:
  def __init__(self, request):
    self.values = {REQUEST_PARAM: request}

  def get(self, key):
    return self.values.get(key)

  def remove(self, key):
    self.values.pop(key, None)

  def put(self, key, value, block=False):
    self.values[key] = value


def test_card_params_service_rejects_request_when_safety_was_not_configured(tmp_path):
  params = FakeControllerParams({"test_id": "blocked-session", "direction": "left"})
  controller = TeslaTurnSignalRealtimeController(configured=False)

  controller.service_params(params, now_nanos=1_000_000_000, log_path=str(tmp_path / "validation.log"))

  assert REQUEST_PARAM not in params.values
  assert params.values[RESULT_PARAM]["test_id"] == "blocked-session"
  assert params.values[RESULT_PARAM]["result"] == "BLOCKED"


def test_web_client_uses_params_request_without_subscribing_to_can(mocker):
  sub_sock = mocker.patch("cereal.messaging.sub_sock", side_effect=AssertionError("web must not subscribe to CAN"))
  assert send_validation_pulse("right", params=FakeParams(), timeout_s=0.1, poll_interval_s=0.0)
  sub_sock.assert_not_called()
