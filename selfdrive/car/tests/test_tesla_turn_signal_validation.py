import json

from opendbc.can.packer import CANPacker

from openpilot.selfdrive.car.tesla_turn_signal_controller import (
  create_body_control_frame,
  decode_front_lighting,
  decode_ui_warning,
  persist_validation_records,
  tesla_body_controls_checksum,
)


def test_validation_log_is_disabled_by_default(tmp_path):
  log_path = tmp_path / "turn_signal_validation.log"
  persist_validation_records([{"event": "frame_sent"}], str(log_path))
  assert not log_path.exists()


OBSERVED_BODY_CONTROLS = bytes.fromhex("008802000000b026")


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


def test_validation_recorder_persists_replayable_session(tmp_path, monkeypatch):
  monkeypatch.setattr("openpilot.selfdrive.car.tesla_turn_signal_controller.TURN_SIGNAL_VALIDATION_LOGGING_ENABLED", True)
  log_path = tmp_path / "turn_signal_validation.log"
  records_to_write = [
    {"test_id": "test-session", "direction": "left", "event": "frame_sent", "request": 1,
     "reason": 8, "counter": 12, "data": "008910000000c045"},
    {"test_id": "test-session", "direction": "left", "event": "test_finished", "result": "PASS", "feedback": True},
  ]
  persist_validation_records(records_to_write, str(log_path))

  records = [json.loads(line) for line in log_path.read_text().splitlines()]
  assert [record["event"] for record in records] == ["frame_sent", "test_finished"]
  assert all(record["test_id"] == "test-session" for record in records)
  assert all(record["direction"] == "left" for record in records)
  assert records[0]["request"] == 1
