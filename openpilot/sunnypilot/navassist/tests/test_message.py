from openpilot.cereal import messaging
from openpilot.sunnypilot.navassist.navassistd import fill_nav_assist_message
from openpilot.sunnypilot.navassist.types import Maneuver, NavAssistState, SpeedSource


def test_fill_message_preserves_safe_units_and_enums():
  message = messaging.new_message("navAssistSP")
  state = NavAssistState(connected=True, data_valid=True, guidance_valid=True, stale=False,
                         maneuver=Maneuver.TURN_LEFT, maneuver_id=42, distance_to_maneuver_m=30,
                         desired_speed_mps=5, speed_source=SpeedSource.MANEUVER)
  fill_nav_assist_message(message, state, 123)
  assert message.navAssistSP.maneuver == "turnLeft"
  assert message.navAssistSP.speedSource == "maneuver"
  assert message.navAssistSP.desiredSpeedMps == 5
