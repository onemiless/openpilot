import json
from types import SimpleNamespace

from openpilot.selfdrive.car.tesla_can_probe import TeslaCanProbe, decode_tesla_probe_frame


def test_decode_speed_button_and_turn_messages():
  assert decode_tesla_probe_frame(0x238, bytes.fromhex("b0299cdc1f00b660")) == {
    "speed_control_state": 48, "speed_control_action": "UNKNOWN_48",
    "vsl_enable_request": 0, "speed_control_state_inverse": 1,
    "distance_request": 41, "turn_lever_state": 0, "high_beam_lever_state": 3,
    "wiper_wash_pressed": 1, "rear_wiper_switch_position": 2,
    "steering_wheel_lever_state": 4, "steering_wheel_condition_fault": 1,
    "steering_wheel_condition_pressed": 1, "horn_pressed": 3,
    "steering_wheel_switch_mask": 31, "wiper_switch_position": 6,
    "counter": 11, "checksum": 0x60,
  }
  assert decode_tesla_probe_frame(0x249, bytes.fromhex("340b0200")) == {
    "turn_stalk_state": 2, "counter": 11, "checksum": 0x34,
  }
  assert decode_tesla_probe_frame(0x3E9, bytes([0, 2, 16, 0x21, 0, 0, 0xC0, 0x66])) == {
    "turn_request": 2, "turn_request_reason": 8, "autopilot_active": 1, "acc_active": 1,
    "counter": 12, "checksum": 0x66,
  }


def test_probe_records_bus_direction_and_filters_unrelated_frames(tmp_path):
  log_path = tmp_path / "probe.log"
  probe = TeslaCanProbe(True, str(log_path))
  probe.update_can([
    (1_000_000_000, [
      (0x238, bytes([32, 0, 0, 0, 0, 0, 0x30, 0x77]), 1),
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


def test_probe_summarizes_stw_payload_changes_per_direction(tmp_path):
  log_path = tmp_path / "probe.log"
  probe = TeslaCanProbe(True, str(log_path))
  probe.update_can([
    (1_000_000_000, [
      (0x238, bytes.fromhex("b0299cdc1f00b660"), 1),
      (0x238, bytes.fromhex("b0299cdc1f00c670"), 1),  # counter/checksum only
      (0x238, bytes.fromhex("a02d9cd41f00d66c"), 1),  # physical payload changed
      (0x238, bytes.fromhex("100000000000e0aa"), 0x81),  # separate TX stream
    ]),
  ])
  probe.flush()

  records = [json.loads(line) for line in log_path.read_text().splitlines()]
  changes = [record for record in records if record["event"] == "stw_action_change"]
  assert len(changes) == 3
  assert changes[1]["direction"] == "rx"
  assert changes[1]["changed_bytes"] == [0, 1, 3]
  assert changes[1]["previous_payload"] == "b0299cdc1f0006"
  assert changes[1]["payload"] == "a02d9cd41f0006"
  assert changes[2]["direction"] == "txEcho"
  assert changes[2]["decoded"]["speed_control_action"] == "UP_1ST"
