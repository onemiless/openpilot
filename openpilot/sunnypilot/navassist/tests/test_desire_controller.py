from types import SimpleNamespace as ns

from openpilot.sunnypilot.navassist.config import NavAssistParams
from openpilot.sunnypilot.navassist.desire_controller import NavDesireController
from openpilot.sunnypilot.navassist.types import LateralRequest, Maneuver
from openpilot.cereal import messaging


PARAMS = NavAssistParams(True, False, True, True, False, False, True, 1.2, 30 / 3.6)


def car(**overrides):
  values = {"vEgo": 8.0, "leftBlinker": True, "rightBlinker": False, "brakePressed": False,
            "trailerConnected": False}
  values.update(overrides)
  return ns(**values)


def nav(mid=1):
  return ns(maneuver=Maneuver.TURN_LEFT, sessionId="session", maneuverId=mid,
            dataValid=True, stale=False, offRoute=False, distanceToManeuverM=35.0)


def test_driver_confirmed_turn_is_one_shot():
  controller = NavDesireController()
  assert controller.update(nav(), True, PARAMS, car(), True).request == LateralRequest.TURN_LEFT
  assert controller.update(nav(), True, PARAMS, car(), True).request == LateralRequest.NONE


def test_opposite_signal_cancels_same_maneuver():
  controller = NavDesireController()
  assert controller.update(nav(), True, PARAMS, car(leftBlinker=False, rightBlinker=True), True).request == LateralRequest.NONE
  assert controller.update(nav(), True, PARAMS, car(), True).request == LateralRequest.NONE


def test_accepts_capnp_maneuver_enum():
  message = messaging.new_message("navAssistSP")
  message.navAssistSP.maneuver = "turnLeft"
  message.navAssistSP.sessionId = "session"
  message.navAssistSP.maneuverId = 1
  message.navAssistSP.dataValid = True
  message.navAssistSP.distanceToManeuverM = 35
  assert NavDesireController().update(message.navAssistSP, True, PARAMS, car(), True).request == LateralRequest.TURN_LEFT
