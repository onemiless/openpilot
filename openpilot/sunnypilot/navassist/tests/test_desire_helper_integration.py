from types import SimpleNamespace as ns

from openpilot.cereal import log, messaging
from openpilot.common.params import Params
from openpilot.common.test import OpenpilotTestCase
from openpilot.selfdrive.controls.lib.desire_helper import DesireHelper


class TestNavAssistDesireHelper(OpenpilotTestCase):
  def test_matching_real_signal_emits_one_turn_desire(self):
    params = Params()
    params.put("NavAssistEnabled", True, block=True)
    params.put("NavAssistShadowMode", False, block=True)
    params.put("NavAssistTurnControl", True, block=True)
    params.put("NavAssistRequireTurnSignal", True, block=True)
    params.put("NavAssistTurnMaxSpeedKph", 30, block=True)

    nav_message = messaging.new_message("navAssistSP")
    nav = nav_message.navAssistSP
    nav.dataValid = True
    nav.guidanceValid = True
    nav.maneuver = "turnLeft"
    nav.maneuverId = 9
    nav.sessionId = "session"
    nav.distanceToManeuverM = 35

    car = ns(vEgo=8.0, leftBlinker=True, rightBlinker=False, leftBlindspot=False, rightBlindspot=False,
             steeringPressed=False, steeringTorque=0.0, brakePressed=False, trailerConnected=False)
    helper = DesireHelper()
    helper.update(car, True, 1.0, nav_assist=nav, nav_assist_valid=True)
    assert helper.desire == log.Desire.turnLeft
    helper.update(car, True, 1.0, nav_assist=nav, nav_assist_valid=True)
    assert helper.desire == log.Desire.none

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
             steeringPressed=False, steeringTorque=0.0, brakePressed=False, trailerConnected=False)
    helper = DesireHelper()
    helper.update(car, True, 1.0, nav_assist=nav, nav_assist_valid=True)
    assert helper.desire == log.Desire.none
