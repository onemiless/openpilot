import json
from types import SimpleNamespace

from opendbc.can.packer import CANPacker

import openpilot.selfdrive.debug.tesla_turn_signal_test as turn_signal_test
from openpilot.selfdrive.debug.tesla_turn_signal_test import ValidationRecorder, decode_ui_warning, send_validation_pulse


def test_decode_ui_warning_blinker_feedback():
  packer = CANPacker("tesla_model3_party")
  left = packer.make_can_msg("UI_warning", 0, {"leftBlinkerBlinking": 2, "rightBlinkerBlinking": 0})
  right = packer.make_can_msg("UI_warning", 0, {"leftBlinkerBlinking": 0, "rightBlinkerBlinking": 1})
  assert decode_ui_warning(left[1]) == {"left_blinker": True, "right_blinker": False,
                                        "left_blinker_state": 2, "right_blinker_state": 0}
  assert decode_ui_warning(right[1]) == {"left_blinker": False, "right_blinker": True,
                                         "left_blinker_state": 0, "right_blinker_state": 1}


def test_validation_does_not_require_car_state_or_car_control(monkeypatch, tmp_path):
  baseline = SimpleNamespace(address=0x249, src=1, dat=bytes.fromhex("9b000000"))
  event = SimpleNamespace(can=[baseline])
  sendcan = SimpleNamespace(sent=[], send=lambda message: sendcan.sent.append(message))

  monkeypatch.setattr(turn_signal_test, "Params", lambda: SimpleNamespace(get_bool=lambda _key: True))
  monkeypatch.setattr(turn_signal_test.messaging, "sub_sock", lambda *_args, **_kwargs: object())
  monkeypatch.setattr(turn_signal_test.messaging, "pub_sock", lambda *_args, **_kwargs: sendcan)
  monkeypatch.setattr(turn_signal_test.messaging, "recv_one_or_none", lambda _sock: event)
  monkeypatch.setattr(turn_signal_test.messaging, "SubMaster", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not subscribe")))
  monkeypatch.setattr(turn_signal_test, "observe_can", lambda *_args, **_kwargs: (False, True, False))

  assert send_validation_pulse("left", str(tmp_path / "validation.log")) is False
  assert len(sendcan.sent) == 5


def test_validation_recorder_persists_replayable_session(tmp_path):
  log_path = tmp_path / "turn_signal_validation.log"
  recorder = ValidationRecorder("left", str(log_path), test_id="test-session")
  recorder.record("frame_sent", state=6, counter=4, data="f7040600")
  recorder.record("test_finished", result="PASS", feedback=True)

  records = [json.loads(line) for line in log_path.read_text().splitlines()]
  assert [record["event"] for record in records] == ["frame_sent", "test_finished"]
  assert all(record["test_id"] == "test-session" for record in records)
  assert all(record["direction"] == "left" for record in records)
  assert records[0]["data"] == "f7040600"
