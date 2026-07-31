from openpilot.selfdrive.debug.tesla_speed_button_test import (
  SpeedButtonAction,
  create_speed_button_frame,
  decode_right_scroll_ticks,
  is_original_vehicle_speed_frame,
)


OBSERVED_IDLE_FRAME = bytes.fromhex("010000c000000000")


def test_original_vehicle_filter_accepts_only_switch_status_mux_one_rx():
  assert is_original_vehicle_speed_frame(0x3C2, 1, OBSERVED_IDLE_FRAME)
  assert not is_original_vehicle_speed_frame(0x3C2, 0x81, OBSERVED_IDLE_FRAME)
  assert not is_original_vehicle_speed_frame(0x3C2, 0xC1, OBSERVED_IDLE_FRAME)
  assert not is_original_vehicle_speed_frame(0x238, 1, OBSERVED_IDLE_FRAME)
  assert not is_original_vehicle_speed_frame(0x3C2, 1, bytes.fromhex("0000000000000000"))


def test_right_scroll_ticks_are_signed_six_bit_values():
  assert decode_right_scroll_ticks(OBSERVED_IDLE_FRAME) == 0
  assert decode_right_scroll_ticks(bytes.fromhex("010000c100000000")) == 1
  assert decode_right_scroll_ticks(bytes.fromhex("010000ff00000000")) == -1


def test_validation_frames_clone_vehicle_payload_and_change_only_right_scroll_ticks():
  increase = create_speed_button_frame(OBSERVED_IDLE_FRAME, SpeedButtonAction.increase)
  decrease = create_speed_button_frame(OBSERVED_IDLE_FRAME, SpeedButtonAction.decrease)

  assert increase.hex() == "010000c100000000"
  assert decrease.hex() == "010000ff00000000"
  assert [index for index, pair in enumerate(zip(OBSERVED_IDLE_FRAME, increase, strict=True)) if pair[0] != pair[1]] == [3]
  assert [index for index, pair in enumerate(zip(OBSERVED_IDLE_FRAME, decrease, strict=True)) if pair[0] != pair[1]] == [3]
