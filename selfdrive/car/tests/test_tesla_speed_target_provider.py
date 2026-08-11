from types import SimpleNamespace

import pytest

from openpilot.selfdrive.car.tesla_speed_target_provider import TARGET_MAX_AGE_NS, TeslaSpeedTargetProvider


class FakeParams:
  def __init__(self, offset):
    self.offset = offset

  def get_int(self, key):
    assert key == "AutoRoadSpeedLimitOffset"
    return self.offset


def test_provider_uses_active_carrot_road_limit_and_offset():
  provider = TeslaSpeedTargetProvider(FakeParams(5))
  carrot = SimpleNamespace(activeCarrot=2, nRoadLimitSpeed=70)
  car_state = SimpleNamespace(speedLimit=0)
  target = provider.update(carrot, car_state, 10, True, 10 + TARGET_MAX_AGE_NS)
  assert target.valid
  assert target.speed_kph == 75
  assert target.speed_mps == pytest.approx(75 / 3.6)
  assert target.source == "carrot"


def test_provider_rejects_inactive_carrot_default_and_ignores_vehicle_limit():
  provider = TeslaSpeedTargetProvider(FakeParams(0))
  inactive_carrot = SimpleNamespace(activeCarrot=0, nRoadLimitSpeed=30)
  target = provider.update(inactive_carrot, SimpleNamespace(speedLimit=80), 100, True, 100)
  assert not target.valid


def test_provider_rejects_stale_or_disabled_offset():
  carrot = SimpleNamespace(activeCarrot=2, nRoadLimitSpeed=70)
  car_state = SimpleNamespace(speedLimit=0)
  stale = TeslaSpeedTargetProvider(FakeParams(0)).update(
    carrot, car_state, 1, True, TARGET_MAX_AGE_NS + 2,
  )
  assert not stale.valid and stale.source == "stale"

  disabled = TeslaSpeedTargetProvider(FakeParams(-1)).update(carrot, car_state, 1, True, 1)
  assert not disabled.valid
