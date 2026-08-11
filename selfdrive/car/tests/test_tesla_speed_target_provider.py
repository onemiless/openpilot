from types import SimpleNamespace

import pytest

from openpilot.selfdrive.car.tesla_speed_target_provider import (
  TARGET_MAX_AGE_NS, TESLA_TARGET_MAX_AGE_NS, TeslaSpeedTargetProvider,
)


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


def test_provider_rejects_inactive_carrot_default_without_a_vehicle_limit():
  provider = TeslaSpeedTargetProvider(FakeParams(0))
  inactive_carrot = SimpleNamespace(activeCarrot=0, nRoadLimitSpeed=30)
  target = provider.update(inactive_carrot, SimpleNamespace(speedLimit=80), 100, True, 100)
  assert not target.valid


def test_provider_uses_confirmed_fresh_tesla_fused_limit_as_fallback():
  provider = TeslaSpeedTargetProvider(FakeParams(5))
  inactive_carrot = SimpleNamespace(activeCarrot=0, nRoadLimitSpeed=30)
  first = provider.update(inactive_carrot, SimpleNamespace(), 100, True, 1_000,
                          vehicle_limit_kph=70, vehicle_limit_valid=True, vehicle_limit_nanos=900)
  assert not first.valid

  confirmed = provider.update(inactive_carrot, SimpleNamespace(), 100, True, 2_000,
                              vehicle_limit_kph=70, vehicle_limit_valid=True, vehicle_limit_nanos=1_900)
  assert confirmed.valid
  assert confirmed.source == "tesla_fused"
  assert confirmed.speed_kph == 75
  assert confirmed.speed_mps == pytest.approx(75 / 3.6)


def test_provider_does_not_count_cached_tesla_message_twice():
  provider = TeslaSpeedTargetProvider(FakeParams(0))
  inactive_carrot = SimpleNamespace(activeCarrot=0, nRoadLimitSpeed=30)
  for now_nanos in (1_000, 1_100, 1_200):
    target = provider.update(inactive_carrot, SimpleNamespace(), 100, True, now_nanos,
                             vehicle_limit_kph=70, vehicle_limit_valid=True, vehicle_limit_nanos=900)
    assert not target.valid


def test_provider_prefers_fresh_active_carrot_over_confirmed_tesla_limit():
  provider = TeslaSpeedTargetProvider(FakeParams(0))
  inactive = SimpleNamespace(activeCarrot=0, nRoadLimitSpeed=30)
  provider.update(inactive, SimpleNamespace(), 100, True, 1_000,
                  vehicle_limit_kph=70, vehicle_limit_valid=True, vehicle_limit_nanos=900)
  provider.update(inactive, SimpleNamespace(), 100, True, 2_000,
                  vehicle_limit_kph=70, vehicle_limit_valid=True, vehicle_limit_nanos=1_900)

  active = SimpleNamespace(activeCarrot=2, nRoadLimitSpeed=90)
  target = provider.update(active, SimpleNamespace(), 2_000, True, 2_100,
                           vehicle_limit_kph=70, vehicle_limit_valid=True, vehicle_limit_nanos=1_900)
  assert target.valid
  assert target.source == "carrot"
  assert target.speed_kph == 90


def test_provider_rejects_stale_tesla_limit_and_requires_two_new_frames_after_gap():
  provider = TeslaSpeedTargetProvider(FakeParams(0))
  inactive = SimpleNamespace(activeCarrot=0, nRoadLimitSpeed=30)
  stale = provider.update(inactive, SimpleNamespace(), 0, False, TESLA_TARGET_MAX_AGE_NS + 2,
                          vehicle_limit_kph=70, vehicle_limit_valid=True, vehicle_limit_nanos=1)
  assert not stale.valid and stale.source == "stale"

  first_new = provider.update(inactive, SimpleNamespace(), 0, False, TESLA_TARGET_MAX_AGE_NS + 100,
                              vehicle_limit_kph=70, vehicle_limit_valid=True,
                              vehicle_limit_nanos=TESLA_TARGET_MAX_AGE_NS + 90)
  assert not first_new.valid
  second_new = provider.update(inactive, SimpleNamespace(), 0, False, TESLA_TARGET_MAX_AGE_NS + 200,
                               vehicle_limit_kph=70, vehicle_limit_valid=True,
                               vehicle_limit_nanos=TESLA_TARGET_MAX_AGE_NS + 190)
  assert second_new.valid and second_new.source == "tesla_fused"


def test_provider_rejects_target_outside_supported_range_after_offset():
  provider = TeslaSpeedTargetProvider(FakeParams(10))
  carrot = SimpleNamespace(activeCarrot=2, nRoadLimitSpeed=195)
  target = provider.update(carrot, SimpleNamespace(), 100, True, 100)
  assert not target.valid and target.source == "invalid"


def test_provider_rejects_stale_or_disabled_offset():
  carrot = SimpleNamespace(activeCarrot=2, nRoadLimitSpeed=70)
  car_state = SimpleNamespace(speedLimit=0)
  stale = TeslaSpeedTargetProvider(FakeParams(0)).update(
    carrot, car_state, 1, True, TARGET_MAX_AGE_NS + 2,
  )
  assert not stale.valid and stale.source == "stale"

  disabled = TeslaSpeedTargetProvider(FakeParams(-1)).update(carrot, car_state, 1, True, 1)
  assert not disabled.valid
