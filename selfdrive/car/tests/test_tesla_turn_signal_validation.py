from types import SimpleNamespace
import json

from cereal import car

from openpilot.selfdrive.debug.tesla_turn_signal_test import ValidationRecorder, validation_guard


def make_state():
  CS = SimpleNamespace(
    gearShifter=car.CarState.GearShifter.park,
    standstill=True,
    vEgo=0.0,
    brakePressed=True,
    cruiseState=SimpleNamespace(enabled=False),
  )
  CC = SimpleNamespace(enabled=False, latActive=False, longActive=False)
  return CS, CC


def test_validation_guard_accepts_parked_brake_held_vehicle():
  CS, CC = make_state()
  CS.brakePressed = False
  assert validation_guard(CS, CC) is None


def test_validation_guard_blocks_motion_and_active_controls():
  CS, CC = make_state()
  CS.gearShifter = car.CarState.GearShifter.drive
  assert validation_guard(CS, CC) == "vehicle is not in Park"

  CS, CC = make_state()
  CS.vEgo = 0.2
  assert validation_guard(CS, CC) == "vehicle is not stationary"

  CS, CC = make_state()
  CC.enabled = True
  assert validation_guard(CS, CC) == "openpilot/sunnypilot controls are active"

  CS, CC = make_state()
  assert validation_guard(CS, CC, device_started=True) == "device is not in Settings/Offroad state"


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
