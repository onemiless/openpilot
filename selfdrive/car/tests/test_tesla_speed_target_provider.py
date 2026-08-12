from openpilot.selfdrive.car.tesla_speed_target_provider import TESLA_TARGET_MAX_AGE_NS, TeslaSpeedTargetProvider


class FakeParams:
  def __init__(self, offset):
    self.offset = offset

  def get_int(self, key):
    assert key == "AutoRoadSpeedLimitOffset"
    return self.offset


def test_provider_uses_only_confirmed_tesla_fused_limit_plus_offset():
  provider = TeslaSpeedTargetProvider(FakeParams(5))
  first = provider.update(80, True, 100, 100)
  assert not first.valid and first.source == "confirming"
  target = provider.update(80, True, 200, 200)
  assert target.valid
  assert target.source == "tesla_fused"
  assert target.fused_limit_kph == 80
  assert target.offset_kph == 5
  assert target.speed_kph == 85


def test_provider_rejects_stale_disabled_and_out_of_range_targets():
  stale = TeslaSpeedTargetProvider(FakeParams(0)).update(80, True, 1, TESLA_TARGET_MAX_AGE_NS + 2)
  assert not stale.valid and stale.source == "stale"
  disabled = TeslaSpeedTargetProvider(FakeParams(-1)).update(80, True, 1, 1)
  assert not disabled.valid and disabled.source == "disabled"

  provider = TeslaSpeedTargetProvider(FakeParams(100))
  provider.update(120, True, 100, 100)
  invalid = provider.update(120, True, 200, 200)
  assert not invalid.valid and invalid.source == "out_of_range"


def test_provider_does_not_confirm_the_same_cached_frame_twice():
  provider = TeslaSpeedTargetProvider(FakeParams(0))
  for now in (100, 200, 300):
    assert not provider.update(80, True, 100, now).valid
