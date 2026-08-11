import pytest

from opendbc.car.tesla.carstate import normalize_tesla_speed_limit


def test_tesla_speed_limit_normalizes_metric_and_imperial_display_units():
  assert normalize_tesla_speed_limit(30, "KPH") == 30
  assert normalize_tesla_speed_limit(65, "MPH") == pytest.approx(104.60736)


@pytest.mark.parametrize("display_limit, units", [
  (0, "KPH"),
  (155, "KPH"),  # Raw enum 31 (NONE) after the DBC scale of five.
  (25, "KPH"),
  (95, "MPH"),
  (float("nan"), "KPH"),
  (70, None),
])
def test_tesla_speed_limit_rejects_sna_none_unknown_units_and_unsupported_range(display_limit, units):
  assert normalize_tesla_speed_limit(display_limit, units) is None
