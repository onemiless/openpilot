from types import SimpleNamespace as ns

from openpilot.cereal import log, messaging
from openpilot.common.params import Params
from openpilot.common.test import OpenpilotTestCase
from openpilot.selfdrive.controls.lib.desire_helper import DesireHelper


class TestNavAssistDesireHelper(OpenpilotTestCase):
  @staticmethod
  def _nav():
    nav_message = messaging.new_message("navAssistSP")
    nav = nav_message.navAssistSP
    nav.dataValid = True
    nav.guidanceValid = True
    nav.maneuver = "turnLeft"
    nav.maneuverId = 9
    nav.sessionId = "session"
    nav.distanceToManeuverM = 35
    return nav_message, nav

  def test_matching_real_signal_emits_one_turn_desire(self):
    params = Params()
    params.put("NavAssistEnabled", True, block=True)
    params.put("NavAssistShadowMode", False, block=True)
    params.put("NavAssistTurnControl", True, block=True)
    params.put("NavAssistRequireTurnSignal", True, block=True)
    params.put("NavAssistTurnMaxSpeedKph", 30, block=True)

    _nav_message, nav = self._nav()

    car = ns(vEgo=8.0, leftBlinker=True, rightBlinker=False, leftBlindspot=False, rightBlindspot=False,
             steeringPressed=False, steeringTorque=0.0, brakePressed=False)
    helper = DesireHelper()
    helper.update(car, True, 1.0, nav_assist=nav, nav_assist_valid=True)
    assert helper.desire == log.Desire.turnLeft
    helper.update(car, True, 1.0, nav_assist=nav, nav_assist_valid=True)
    assert helper.desire == log.Desire.none
    assert helper.nav_output.reason == "consumed"

  def test_existing_blindspot_and_lane_turn_speed_gates_are_preserved(self):
    params = Params()
    params.put("NavAssistEnabled", True, block=True)
    params.put("NavAssistShadowMode", False, block=True)
    params.put("NavAssistTurnControl", True, block=True)
    params.put("LaneTurnValue", 10.0, block=True)
    _nav_message, nav = self._nav()

    blocked = ns(vEgo=4.0, leftBlinker=True, rightBlinker=False, leftBlindspot=True, rightBlindspot=False,
                 steeringPressed=False, steeringTorque=0.0, brakePressed=False)
    helper = DesireHelper()
    helper.update(blocked, True, 1.0, nav_assist=nav, nav_assist_valid=True)
    assert helper.desire == log.Desire.none

    too_fast = ns(vEgo=5.0, leftBlinker=True, rightBlinker=False, leftBlindspot=False, rightBlindspot=False,
                  steeringPressed=False, steeringTorque=0.0, brakePressed=False)
    helper = DesireHelper()
    helper.update(too_fast, True, 1.0, nav_assist=nav, nav_assist_valid=True)
    assert helper.desire == log.Desire.none

  def test_real_carstate_message_reaches_desire_helper_without_schema_assumptions(self):
    params = Params()
    params.put("NavAssistEnabled", True, block=True)
    params.put("NavAssistShadowMode", False, block=True)
    params.put("NavAssistTurnControl", True, block=True)
    _nav_message, nav = self._nav()
    car_message = messaging.new_message("carState")
    car = car_message.carState
    car.vEgo = 8.0
    car.leftBlinker = True
    helper = DesireHelper()
    helper.update(car, True, 1.0, nav_assist=nav, nav_assist_valid=True)
    assert helper.desire == log.Desire.turnLeft

  def test_shadow_never_changes_baseline_desire(self):
    params = Params()
    params.put("NavAssistEnabled", True, block=True)
    params.put("NavAssistShadowMode", True, block=True)
    params.put("NavAssistTurnControl", True, block=True)
    nav_message = messaging.new_message("navAssistSP")
    nav = nav_message.navAssistSP
    nav.dataValid = True
    nav.maneuver = "turnLeft"
    nav.maneuverId = 1
    nav.sessionId = "session"
    nav.distanceToManeuverM = 35
    car = ns(vEgo=8.0, leftBlinker=False, rightBlinker=False, leftBlindspot=False, rightBlindspot=False,
             steeringPressed=False, steeringTorque=0.0, brakePressed=False)
    helper = DesireHelper()
    helper.update(car, True, 1.0, nav_assist=nav, nav_assist_valid=True)
    assert helper.desire == log.Desire.none
    assert helper.nav_output.would_request
    assert helper.nav_output.reason == "shadow"
