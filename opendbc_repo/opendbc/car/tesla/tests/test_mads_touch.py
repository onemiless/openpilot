from opendbc.car.interfaces import CarInterfaceBase
from opendbc.car.structs import CarState as CarStateStruct
from opendbc.car.tesla.carstate import CarState as TeslaCarState
from opendbc.car.tesla.mads_touch import MadsTouchInput, TESLA_UI_STATUS_2
from opendbc.car.tesla.values import CAR
from opendbc.safety import ALTERNATIVE_EXPERIENCE


ButtonType = CarStateStruct.ButtonEvent.Type


def touch_frame(points, length=8):
  data = bytearray(length)
  if length > 3:
    data[3] = points
  return bytes(data)


def test_three_finger_press_and_release_produce_one_lkas_edge_each():
  touch = MadsTouchInput(True)

  touch.observe(TESLA_UI_STATUS_2, touch_frame(3), 1)
  pressed = touch.take_button_events()
  assert [(event.type, event.pressed) for event in pressed] == [(ButtonType.lkas, True)]

  touch.observe(TESLA_UI_STATUS_2, touch_frame(3), 1)
  assert touch.take_button_events() == []

  touch.observe(TESLA_UI_STATUS_2, touch_frame(0), 1)
  released = touch.take_button_events()
  assert [(event.type, event.pressed) for event in released] == [(ButtonType.lkas, False)]


def test_other_counts_bus_address_and_length_are_ignored():
  touch = MadsTouchInput(True)
  touch.observe(TESLA_UI_STATUS_2, touch_frame(2), 1)
  touch.observe(TESLA_UI_STATUS_2, touch_frame(3), 0)
  touch.observe(TESLA_UI_STATUS_2 + 1, touch_frame(3), 1)
  touch.observe(TESLA_UI_STATUS_2, touch_frame(3, length=7), 1)
  assert touch.take_button_events() == []


def test_touch_input_is_inert_when_mads_is_not_configured():
  touch = MadsTouchInput(False)
  touch.observe(TESLA_UI_STATUS_2, touch_frame(3), 1)
  assert touch.take_button_events() == []


def test_carstate_touch_input_follows_mads_enabled_after_carstate_construction():
  CP = CarInterfaceBase.get_std_params(CAR.TESLA_MODEL_3)
  CP.alternativeExperience = 0
  car_state = TeslaCarState(CP)

  CP.alternativeExperience |= ALTERNATIVE_EXPERIENCE.ENABLE_MADS
  car_state.observe_aux_can(TESLA_UI_STATUS_2, touch_frame(3), 1)
  events = car_state.mads_touch_input.take_button_events()
  assert [(event.type, event.pressed) for event in events] == [(ButtonType.lkas, True)]
