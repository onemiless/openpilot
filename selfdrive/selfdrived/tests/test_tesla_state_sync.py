from openpilot.selfdrive.selfdrived.selfdrived import tesla_car_state_sp_fresh, tesla_longitudinal_source_from_flags


def test_tesla_car_state_sp_freshness_is_bounded():
  assert tesla_car_state_sp_fresh(1_050_000_000, 1_000_000_000)
  assert not tesla_car_state_sp_fresh(1_050_000_001, 1_000_000_000)
  assert not tesla_car_state_sp_fresh(999_999_999, 1_000_000_000)
  assert not tesla_car_state_sp_fresh(1_000_000_000, 0)


def test_tesla_longitudinal_source_flags_are_unambiguous():
  assert tesla_longitudinal_source_from_flags(0) == "sp"
  assert tesla_longitudinal_source_from_flags(32 | 1024) == "dynamicStock"
  assert tesla_longitudinal_source_from_flags(32 | 2048) == "manualStock"
  assert tesla_longitudinal_source_from_flags(32 | 512) == "apHybridStock"
  assert tesla_longitudinal_source_from_flags(32) == "stockUnknown"
