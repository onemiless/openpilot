from types import SimpleNamespace as ns

from opendbc.sunnypilot.car.tesla.values import TeslaFlagsSP
from openpilot.sunnypilot.navassist.control_policy import nav_longitudinal_allowed


class FakeSM(dict):
  def __init__(self, flags=0):
    super().__init__(
      carControl=ns(enabled=True, longActive=True, cruiseControl=ns(override=False)),
      carState=ns(gasPressed=False, brakePressed=False),
      carStateSP=ns(flags=flags),
    )
    self.seen = {"carStateSP": True}
    self.alive = {"carStateSP": True}
    self.valid = {"carStateSP": True}
    self.logMonoTime = {"carState": 100_000_000, "carStateSP": 100_000_000}


def test_tesla_stock_owner_blocks_all_navigation_longitudinal_sources():
  sm = FakeSM(int(TeslaFlagsSP.STOCK_LONGITUDINAL_ACTIVE))
  assert not nav_longitudinal_allowed(sm, True)
  assert nav_longitudinal_allowed(sm, False)


def test_driver_override_blocks_navigation_longitudinal_sources():
  sm = FakeSM()
  sm["carState"].gasPressed = True
  assert not nav_longitudinal_allowed(sm, True)
