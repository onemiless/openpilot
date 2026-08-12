import math

import pytest

from opendbc.car.tesla.carstate import normalize_tesla_speed_limit


@pytest.mark.parametrize(("value", "units", "expected"), [
  (80.0, "KPH", 80.0),
  (50.0, "MPH", 80.4672),
])
def test_normalize_tesla_speed_limit(value, units, expected):
  assert normalize_tesla_speed_limit(value, units) == pytest.approx(expected)


@pytest.mark.parametrize(("value", "units"), [
  (0.0, "KPH"), (25.0, "KPH"), (155.0, "KPH"), (95.0, "MPH"),
  (math.nan, "KPH"), (80.0, "UNKNOWN"),
])
def test_reject_invalid_tesla_speed_limit(value, units):
  assert normalize_tesla_speed_limit(value, units) is None
