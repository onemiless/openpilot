from opendbc.car.structs import CarState
from opendbc.car.tesla.mads_touch import MadsTouchInput, TESLA_UI_STATUS_2


ButtonType = CarState.ButtonEvent.Type


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
