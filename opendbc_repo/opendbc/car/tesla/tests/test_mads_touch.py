from opendbc.car.structs import CarState
from opendbc.car.tesla.mads_touch import MadsTouchInput, TESLA_UI_STATUS_2


ButtonType = CarState.ButtonEvent.Type


def touch_frame(points, length=8):
  data = bytearray(length)
  if length > 3:
    data[3] = points
  return bytes(data)


def test_three_finger_press_hold_release_and_repress_have_exact_edges():
  touch = MadsTouchInput(True)

  touch.observe(TESLA_UI_STATUS_2, touch_frame(3), 1)
  assert [(event.type, event.pressed) for event in touch.take_button_events()] == [(ButtonType.lkas, True)]

  touch.observe(TESLA_UI_STATUS_2, touch_frame(3), 1)
  assert touch.take_button_events() == []

  touch.observe(TESLA_UI_STATUS_2, touch_frame(0), 1)
  assert [(event.type, event.pressed) for event in touch.take_button_events()] == [(ButtonType.lkas, False)]

  touch.observe(TESLA_UI_STATUS_2, touch_frame(3), 1)
  assert [(event.type, event.pressed) for event in touch.take_button_events()] == [(ButtonType.lkas, True)]


def test_other_counts_bus_address_and_length_are_ignored():
  touch = MadsTouchInput(True)
  for points in (1, 2, 4, 5):
    touch.observe(TESLA_UI_STATUS_2, touch_frame(points), 1)
  touch.observe(TESLA_UI_STATUS_2, touch_frame(3), 0)
  touch.observe(TESLA_UI_STATUS_2 + 1, touch_frame(3), 1)
  touch.observe(TESLA_UI_STATUS_2, touch_frame(3, length=7), 1)
  assert touch.take_button_events() == []


def test_touch_input_tracks_late_enable_and_resets_when_disabled():
  touch = MadsTouchInput(False)
  touch.observe(TESLA_UI_STATUS_2, touch_frame(3), 1)
  assert touch.take_button_events() == []

  touch.set_enabled(True)
  touch.observe(TESLA_UI_STATUS_2, touch_frame(3), 1)
  assert [(event.type, event.pressed) for event in touch.take_button_events()] == [(ButtonType.lkas, True)]

  touch.set_enabled(False)
  touch.set_enabled(True)
  touch.observe(TESLA_UI_STATUS_2, touch_frame(3), 1)
  assert [(event.type, event.pressed) for event in touch.take_button_events()] == [(ButtonType.lkas, True)]
