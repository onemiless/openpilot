from types import SimpleNamespace

from openpilot.sunnypilot.lane_topology.ui_bridge import LaneTopologyUIBridge


def model_fixture(frame_id: int, probabilities=(0.9, 0.9, 0.9, 0.9)):
  # Real modelV2 uses right-positive y and orders lines from image-left to image-right.
  lines = tuple(SimpleNamespace(x=(0.0, 5.0, 10.0, 40.0), y=(y,) * 4, z=(1.2,) * 4)
                for y in (-5.4, -1.8, 1.8, 5.4))
  return SimpleNamespace(frameId=frame_id, timestampEof=frame_id * 50_000_000,
                         laneLines=lines, laneLineProbs=probabilities)


def test_ui_bridge_runs_at_four_hz_and_retains_last_result_between_frames():
  bridge = LaneTopologyUIBridge(frame_divisor=5)
  assert bridge.update(model_fixture(1)) is None
  result = bridge.update(model_fixture(5))
  assert result is not None
  assert result.visible_lane_count == 3
  assert result.ego_lane_index_from_left == 1
  assert bridge.update(model_fixture(6)) is result


def test_ui_bridge_fails_closed_on_malformed_model_message():
  bridge = LaneTopologyUIBridge(frame_divisor=1)
  assert bridge.update(SimpleNamespace(frameId=1, timestampEof=1)) is None
  assert bridge.last_error is not None


def test_ui_bridge_reset_drops_stale_onroad_state():
  bridge = LaneTopologyUIBridge(frame_divisor=1)
  assert bridge.update(model_fixture(1)) is not None
  bridge.reset()
  assert bridge.current is None
