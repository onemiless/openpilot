from types import SimpleNamespace as ns

from openpilot.sunnypilot.navassist.config import NavAssistParams
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_planner import LongitudinalPlannerSP


class FakeSM(dict):
  def __init__(self, **values):
    super().__init__(values)
    self.seen = dict.fromkeys(values, True)
    self.alive = dict.fromkeys(values, True)
    self.valid = dict.fromkeys(values, True)
    self.logMonoTime = dict.fromkeys(values, 100_000_000)


def planner(shadow=False):
  result = object.__new__(LongitudinalPlannerSP)
  result.nav_params = NavAssistParams(True, shadow, True, False, False, False, True, 1.2, 30 / 3.6)
  result.openpilot_longitudinal_control = True
  result.is_tesla = False
  return result


def sm():
  return FakeSM(
    carControl=ns(enabled=True, longActive=True, cruiseControl=ns(override=False)),
    carState=ns(gasPressed=False, brakePressed=False),
    navAssistSP=ns(dataValid=True, stale=False, offRoute=False, speedSource="maneuver",
                   desiredSpeedMps=5.0, speedControlDistanceM=50.0),
  )


def test_valid_target_reduces_speed_and_requests_bounded_deceleration():
  target = planner()._get_nav_assist_target(sm(), 10.0, 0.0, 20.0)
  assert target is not None
  assert target[0] == 5.0
  assert -2.5 <= target[1] < 0.0


def test_shadow_and_driver_override_do_not_add_target():
  assert planner(shadow=True)._get_nav_assist_target(sm(), 10.0, 0.0, 20.0) is None
  override = sm()
  override["carState"].gasPressed = True
  assert planner()._get_nav_assist_target(override, 10.0, 0.0, 20.0) is None
