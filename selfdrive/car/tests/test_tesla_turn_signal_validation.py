import json
from types import SimpleNamespace

from opendbc.can.packer import CANPacker

from openpilot.selfdrive.debug.tesla_turn_signal_test import (
  ACTION_FRAME_COUNT,
  ValidationRecorder,
  create_body_control_frame,
  decode_front_lighting,
  decode_ui_warning,
  observe_can,
  tesla_body_controls_checksum,
  create_validation_can_socket,
)


OBSERVED_BODY_CONTROLS = bytes.fromhex("008802000000b026")


def test_validation_sequence_uses_five_action_frames():
  assert ACTION_FRAME_COUNT == 5


def test_validation_can_socket_conflates_high_rate_can_messages(mocker):
  sub_sock = mocker.patch("openpilot.selfdrive.debug.tesla_turn_signal_test.messaging.sub_sock")
  create_validation_can_socket()

  sub_sock.assert_called_once_with("can", conflate=True, timeout=100)


def test_validation_observer_does_not_log_oem_rx_stream(mocker):
  idle_frame = SimpleNamespace(address=0x3E9, src=1, dat=OBSERVED_BODY_CONTROLS)
  event = SimpleNamespace(can=[idle_frame])
  recorder = SimpleNamespace(record=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected log")))

  mocker.patch("openpilot.selfdrive.debug.tesla_turn_signal_test.time.monotonic", side_effect=[0.0, 0.1, 1.0])
  mocker.patch("openpilot.selfdrive.debug.tesla_turn_signal_test.messaging.recv_one_or_none", return_value=event)
  assert observe_can(SimpleNamespace(), recorder, 0.2, "left") == (False, False, False)


def test_decode_ui_warning_blinker_feedback():
  packer = CANPacker("tesla_model3_party")
  left = packer.make_can_msg("UI_warning", 0, {"leftBlinkerBlinking": 2, "rightBlinkerBlinking": 0})
  right = packer.make_can_msg("UI_warning", 0, {"leftBlinkerBlinking": 0, "rightBlinkerBlinking": 1})
  assert decode_ui_warning(left[1]) == {"left_blinker": True, "right_blinker": False,
                                        "left_blinker_state": 2, "right_blinker_state": 0}
  assert decode_ui_warning(right[1]) == {"left_blinker": False, "right_blinker": True,
                                         "left_blinker_state": 0, "right_blinker_state": 1}


def test_decode_front_lighting_blinker_feedback():
  packer = CANPacker("tesla_model3_vehicle")
  left = packer.make_can_msg("ID3F5VCFRONT_lighting", 1, {
    "VCFRONT_turnSignalLeftStatus": 1,
    "VCFRONT_turnSignalRightStatus": 0,
  })
  right = packer.make_can_msg("ID3F5VCFRONT_lighting", 1, {
    "VCFRONT_turnSignalLeftStatus": 0,
    "VCFRONT_turnSignalRightStatus": 1,
  })
  assert decode_front_lighting(left[1])["left_blinker"] is True
  assert decode_front_lighting(left[1])["right_blinker"] is False
  assert decode_front_lighting(right[1])["left_blinker"] is False
  assert decode_front_lighting(right[1])["right_blinker"] is True


def test_body_control_frames_clone_template_and_update_request_counter_checksum():
  assert tesla_body_controls_checksum(OBSERVED_BODY_CONTROLS) == OBSERVED_BODY_CONTROLS[7]

  left = create_body_control_frame(OBSERVED_BODY_CONTROLS, "left", 12)
  right = create_body_control_frame(OBSERVED_BODY_CONTROLS, "right", 12)
  cancel = create_body_control_frame(OBSERVED_BODY_CONTROLS, "cancel", 12)

  assert left.hex() == "008910000000c045"
  assert right.hex() == "008a10000000c046"
  assert cancel.hex() == "008b08000000c03f"
  assert all(left[index] == OBSERVED_BODY_CONTROLS[index] for index in (0, 3, 4, 5))
  assert tesla_body_controls_checksum(left) == left[7]
  assert tesla_body_controls_checksum(right) == right[7]
  assert tesla_body_controls_checksum(cancel) == cancel[7]


def test_validation_recorder_persists_replayable_session(tmp_path):
  log_path = tmp_path / "turn_signal_validation.log"
  recorder = ValidationRecorder("left", str(log_path), test_id="test-session")
  recorder.record("frame_sent", request=1, reason=8, counter=12, data="008910000000c045")
  recorder.record("test_finished", result="PASS", feedback=True)
  assert not log_path.exists()
  recorder.flush()

  records = [json.loads(line) for line in log_path.read_text().splitlines()]
  assert [record["event"] for record in records] == ["frame_sent", "test_finished"]
  assert all(record["test_id"] == "test-session" for record in records)
  assert all(record["direction"] == "left" for record in records)
  assert records[0]["request"] == 1
