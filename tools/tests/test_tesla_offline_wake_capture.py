from types import SimpleNamespace

from openpilot.tools.tesla_offline_wake_capture import CaptureState


def frame(bus: int, address: int, data: bytes):
  return SimpleNamespace(src=bus, address=address, dat=data)


def test_only_changed_payloads_are_recorded():
  state = CaptureState(record_all=False)

  first = state.record_frames([frame(0, 0x100, b"\x01")], now=10.0)
  repeated = state.record_frames([frame(0, 0x100, b"\x01")], now=11.0)
  changed = state.record_frames([frame(0, 0x100, b"\x02")], now=12.0)

  assert len(first) == 1
  assert repeated == []
  assert changed[0]["previous_data"] == "01"
  assert changed[0]["data"] == "02"


def test_raw_window_can_retain_repeated_payloads():
  state = CaptureState(record_all=False)
  state.record_frames([frame(0, 0x100, b"\x01")], now=10.0)

  records = state.record_frames([frame(0, 0x100, b"\x01")], now=11.0, force_all=True)

  assert len(records) == 1
  assert not records[0]["changed"]


def test_stats_keep_all_frame_counts_even_when_payloads_repeat():
  state = CaptureState(record_all=False)

  state.record_frames([frame(0, 0x100, b"\x01"), frame(1, 0x200, b"\x02")], now=10.0)
  state.record_frames([frame(0, 0x100, b"\x01")], now=10.1)
  stats = state.consume_second_stats(now=11.0)

  assert stats["frame_counts"] == {0: 2, 1: 1}
  assert stats["changed_counts"] == {0: 1, 1: 1}
  assert stats["tracked_addresses"] == 2


def test_quiet_interval_arms_then_marks_the_next_activity_as_wake():
  state = CaptureState(record_all=False, last_frame_monotonic=100.0)

  assert state.update_quiet_state(now=399.9, quiet_seconds=300.0) is None
  assert state.update_quiet_state(now=400.0, quiet_seconds=300.0) == "quiet_entered"

  state.record_frames([frame(0, 0x100, b"\x01")], now=401.0)
  assert state.update_quiet_state(now=401.0, quiet_seconds=300.0) == "wake_activity"
  assert state.wake_detected
