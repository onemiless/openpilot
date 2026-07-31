import json
from types import SimpleNamespace

from openpilot.selfdrive.car.tesla_can_probe import TeslaCanProbe, decode_tesla_probe_frame


def test_decode_speed_wheel_and_turn_messages():
  assert decode_tesla_probe_frame(0x3C2, bytes.fromhex("010000ff00000000")) == {
    "switch_status_index": 1,
    "left_scroll_ticks": 0,
    "right_scroll_ticks": -1,
    "left_pressed": 0,
    "right_pressed": 0,
  }
  assert decode_tesla_probe_frame(0x249, bytes.fromhex("340b0200")) == {
    "turn_stalk_state": 2, "counter": 11, "checksum": 0x34,
  }
  assert decode_tesla_probe_frame(0x3E9, bytes([0, 2, 16, 0x21, 0, 0, 0xC0, 0x66])) == {
    "turn_request": 2, "turn_request_reason": 8, "autopilot_active": 1, "acc_active": 1,
    "counter": 12, "checksum": 0x66,
  }
  assert decode_tesla_probe_frame(0x3F5, bytes.fromhex("0000000000001000")) == {
    "left_blinker": False,
    "right_blinker": True,
    "left_blinker_state": 0,
    "right_blinker_state": 1,
  }


def test_probe_records_bus_direction_and_filters_unrelated_frames(tmp_path):
  log_path = tmp_path / "probe.log"
  probe = TeslaCanProbe(True, str(log_path))
  probe.update_can([
    (1_000_000_000, [
      (0x3C2, bytes.fromhex("0100000100000000"), 1),
      (0x249, bytes.fromhex("f7040600"), 0xC1),
      (0x123, b"\x00", 0),
    ]),
  ])
  probe.flush()

  records = [json.loads(line) for line in log_path.read_text().splitlines()]
  frames = [record for record in records if record["event"] == "can_frame"]
  assert len(frames) == 2
  assert frames[0]["bus"] == 1 and frames[0]["direction"] == "rx"
  assert frames[1]["bus"] == 1 and frames[1]["direction"] == "rejected"


def test_probe_logs_state_changes_and_heartbeat(tmp_path):
  log_path = tmp_path / "probe.log"
  probe = TeslaCanProbe(True, str(log_path))
  cs = SimpleNamespace(
    leftBlinker=False, rightBlinker=False, leftBlindspot=False, rightBlindspot=False,
    brakePressed=False, vEgo=10.0,
    cruiseState=SimpleNamespace(speed=20.0, speedCluster=19.44, enabled=True, available=True),
  )
  cs_sp = SimpleNamespace(speedLimit=22.22, flags=32)

  probe.update_state(cs, cs_sp, 1_000_000_000)
  probe.update_state(cs, cs_sp, 1_100_000_000)
  cs.leftBlinker = True
  probe.update_state(cs, cs_sp, 1_200_000_000)
  probe.flush()

  records = [json.loads(line) for line in log_path.read_text().splitlines()]
  states = [record for record in records if record["event"] == "car_state"]
  assert len(states) == 2
  assert states[-1]["left_blinker"] is True
  assert states[-1]["cruise_speed_cluster"] == 19.44


def test_probe_summarizes_speed_wheel_changes_per_direction(tmp_path):
  log_path = tmp_path / "probe.log"
  probe = TeslaCanProbe(True, str(log_path))
  probe.update_can([
    (1_000_000_000, [
      (0x3C2, bytes.fromhex("0100000000000000"), 1),
      (0x3C2, bytes.fromhex("0100000100000000"), 1),
      (0x3C2, bytes.fromhex("0100003f00000000"), 1),
      (0x3C2, bytes.fromhex("0100000100000000"), 0x81),
    ]),
  ])
  probe.flush()

  records = [json.loads(line) for line in log_path.read_text().splitlines()]
  changes = [record for record in records if record["event"] == "speed_wheel_change"]
  assert len(changes) == 4
  assert changes[1]["direction"] == "rx"
  assert changes[1]["previous_right_scroll_ticks"] == 0
  assert changes[1]["right_scroll_ticks"] == 1
  assert changes[2]["right_scroll_ticks"] == -1
  assert changes[3]["direction"] == "txEcho"
