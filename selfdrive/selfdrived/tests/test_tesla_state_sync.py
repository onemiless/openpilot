from openpilot.selfdrive.selfdrived.selfdrived import (
  should_add_radar_can_error,
  tesla_car_state_sp_fresh,
  tesla_longitudinal_source_from_flags,
  tesla_split_control_event_filter_active,
)


def test_tesla_radar_can_error_only_blocks_sp_longitudinal():
  assert not should_add_radar_can_error(False, True)
  assert not should_add_radar_can_error(True, False)
  assert should_add_radar_can_error(True, True)


def test_tesla_car_state_sp_freshness_is_bounded():
  assert tesla_car_state_sp_fresh(1_050_000_000, 1_000_000_000)
  assert not tesla_car_state_sp_fresh(1_050_000_001, 1_000_000_000)
  assert not tesla_car_state_sp_fresh(999_999_999, 1_000_000_000)
  assert not tesla_car_state_sp_fresh(1_000_000_000, 0)


def test_tesla_longitudinal_source_flags_are_unambiguous():
  assert tesla_longitudinal_source_from_flags(0) == "sp"
  assert tesla_longitudinal_source_from_flags(512) == "apHybridSp"
  assert tesla_longitudinal_source_from_flags(32 | 1024) == "dynamicStock"
  assert tesla_longitudinal_source_from_flags(32 | 2048) == "manualStock"
  assert tesla_longitudinal_source_from_flags(32 | 512) == "apHybridStock"
  assert tesla_longitudinal_source_from_flags(32) == "stockUnknown"
  assert tesla_longitudinal_source_from_flags(16384) == "sp"


def test_ap_hybrid_exit_filters_split_control_events_for_one_frame():
  assert tesla_split_control_event_filter_active(False, False, False, True)
  assert tesla_split_control_event_filter_active(False, False, True, True)
  assert tesla_split_control_event_filter_active(False, False, False, False, True)
  assert not tesla_split_control_event_filter_active(False, False, False, False)
