from opendbc.car import structs

from openpilot.selfdrive.controls.lib.desire_helper import DesireHelper, LaneChangeState
from openpilot.sunnypilot.selfdrive.controls.lib.auto_lane_change import AutoLaneChangeMode


def test_blinker_before_lateral_activation_enters_pre_lane_change():
  desire_helper = DesireHelper()
  desire_helper.alc.update_params = lambda: None
  desire_helper.alc.lane_change_set_timer = AutoLaneChangeMode.NUDGE
  desire_helper.lane_turn_controller.update_params = lambda: None
  desire_helper.lane_turn_controller.update_lane_turn = lambda **_: None

  car_state = structs.CarState()
  car_state.vEgo = 30.0
  car_state.leftBlinker = True

  desire_helper.update(car_state, False, 1.0, False, False)
  desire_helper.update(car_state, True, 1.0, False, False)

  assert desire_helper.lane_change_state == LaneChangeState.preLaneChange
