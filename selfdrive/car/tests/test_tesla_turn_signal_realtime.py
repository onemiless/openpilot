from opendbc.can.packer import CANPacker

from openpilot.selfdrive.car.tesla_turn_signal_controller import (
  ACTION_FRAME_COUNT,
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


def test_realtime_controller_sends_five_actions_and_cancel_from_successive_templates():
  controller = TeslaTurnSignalRealtimeController(configured=True)
  controller.submit_request("left-session", "left", 1_000_000_000)

  for index in range(ACTION_FRAME_COUNT):
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

  cancel_template = idle_body_controls(9)
  controller.observe_frame(1_700_000_000, 0x3E9, cancel_template, 1)
  cancel = controller.take_can_sends(1_701_000_000)
  assert len(cancel) == 1
  assert cancel[0].dat == create_body_control_frame(cancel_template, "cancel", 10)
  controller.observe_frame(1_702_000_000, 0x3E9, cancel[0].dat, 0x81)

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
    "action_frames_sent": ACTION_FRAME_COUNT,
    "cancel_sent": True,
  }
  assert [record["event"] for record in records].count("frame_submitted") == ACTION_FRAME_COUNT + 1


def test_realtime_controller_requires_a_new_oem_template_for_each_send():
  controller = TeslaTurnSignalRealtimeController(configured=True)
  controller.submit_request("right-session", "right", 1_000_000_000)
  template = idle_body_controls(4)
  controller.observe_frame(1_100_000_000, 0x3E9, template, 1)

  first = controller.take_can_sends(1_101_000_000)
  assert len(first) == 1
  controller.observe_frame(1_102_000_000, 0x3E9, first[0].dat, 0x81)
  assert controller.take_can_sends(1_103_000_000) == []


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
      "action_frames_sent": ACTION_FRAME_COUNT,
      "cancel_sent": True,
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
