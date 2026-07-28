from openpilot.tools.analyze_tesla_offline_wake_capture import analyze


def test_report_keeps_the_first_wake_frame_for_each_bus():
  report = analyze([
    {"type": "marker", "name": "quiet_entered", "t_monotonic_s": 100.0},
    {"type": "marker", "name": "wake_activity", "t_monotonic_s": 200.0},
    {"type": "frame", "t_monotonic_s": 200.0, "bus": 2, "address": 0x318, "data": "0102"},
    {"type": "frame", "t_monotonic_s": 200.1, "bus": 2, "address": 0x100, "data": "0304"},
    {"type": "frame", "t_monotonic_s": 200.2, "bus": 0, "address": 0x200, "data": "0506"},
  ])

  assert report["quiet_interval_observed"]
  assert report["wake_activity_observed"]
  assert report["wake_bus_candidates"][0]["bus"] == 2
  assert report["wake_bus_candidates"][0]["first_address"] == 0x318
