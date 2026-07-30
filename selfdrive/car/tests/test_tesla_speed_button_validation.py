from openpilot.selfdrive.debug.tesla_speed_button_test import (
  SpeedButtonAction,
  create_speed_button_frame,
  decode_original_speed_button_state,
  is_original_vehicle_speed_frame,
)


OBSERVED_IDLE_FRAME = bytes.fromhex("b02d9cd81f0016c0")


def test_original_vehicle_filter_excludes_device_transmissions():
  assert is_original_vehicle_speed_frame(0x238, 1, OBSERVED_IDLE_FRAME)
  assert not is_original_vehicle_speed_frame(0x238, 0x81, OBSERVED_IDLE_FRAME)
  assert not is_original_vehicle_speed_frame(0x238, 0xC1, OBSERVED_IDLE_FRAME)
  assert not is_original_vehicle_speed_frame(0x249, 1, OBSERVED_IDLE_FRAME)


def test_inverse_encoded_original_vehicle_actions():
  assert decode_original_speed_button_state(0xB0) == SpeedButtonAction.idle
  assert decode_original_speed_button_state(0xA0) == SpeedButtonAction.increase
  assert decode_original_speed_button_state(0x90) == SpeedButtonAction.decrease


def test_validation_frames_clone_received_vehicle_payload():
  increase = create_speed_button_frame(OBSERVED_IDLE_FRAME, SpeedButtonAction.increase, 2)
  decrease = create_speed_button_frame(OBSERVED_IDLE_FRAME, SpeedButtonAction.decrease, 2)
  release = create_speed_button_frame(OBSERVED_IDLE_FRAME, SpeedButtonAction.idle, 3)

  assert increase.hex() == "a02d9cd81f0026c0"  # exact frame observed in the RX-only capture
  assert decrease.hex() == "902d9cd81f0026b0"
  assert release.hex() == "b02d9cd81f0036e0"
