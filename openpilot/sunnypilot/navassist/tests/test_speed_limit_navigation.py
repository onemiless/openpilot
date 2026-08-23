from types import SimpleNamespace as ns

from opendbc.sunnypilot.car.tesla.values import TeslaFlagsSP
from openpilot.cereal import custom
from openpilot.sunnypilot.selfdrive.controls.lib.speed_limit.speed_limit_resolver import SpeedLimitResolver


SpeedLimitSource = custom.LongitudinalPlanSP.SpeedLimit.Source


class FakeSM(dict):
  def __init__(self, flags=0):
    super().__init__(
      carControl=ns(enabled=True, longActive=True, cruiseControl=ns(override=False)),
      carState=ns(gasPressed=False, brakePressed=False),
      carStateSP=ns(flags=flags),
      navAssistSP=ns(dataValid=True, speedValid=True, stale=False, offRoute=False, roadLimitMps=20.0),
    )
    self.seen = {"navAssistSP": True, "carStateSP": True}
    self.alive = {"navAssistSP": True, "carStateSP": True}
    self.valid = {"navAssistSP": True, "carStateSP": True}
    self.logMonoTime = {"carState": 100_000_000, "carStateSP": 100_000_000}


def resolver(is_tesla):
  result = object.__new__(SpeedLimitResolver)
  result.is_tesla = is_tesla
  result.nav_assist_enabled = True
  result.nav_assist_shadow = False
  result.nav_assist_speed_control = True
  result.limit_solutions = dict.fromkeys(SpeedLimitSource.schema.enumerants.values(), 0.0)
  result.distance_solutions = dict.fromkeys(SpeedLimitSource.schema.enumerants.values(), 0.0)
  return result


def test_navigation_road_limit_obeys_tesla_owner():
  stock = FakeSM(int(TeslaFlagsSP.STOCK_LONGITUDINAL_ACTIVE))
  target = resolver(True)
  target._get_from_navigation(stock)
  assert target.limit_solutions[SpeedLimitSource.navigation] == 0.0

  sp = FakeSM()
  target._get_from_navigation(sp)
  assert target.limit_solutions[SpeedLimitSource.navigation] == 20.0
