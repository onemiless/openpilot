from openpilot.selfdrive.ui.sunnypilot.onroad.smart_cruise_control import (
  AP_HYBRID_ACTIVE,
  AP_HYBRID_STOCK_LATERAL_ACTIVE,
  STOCK_LONGITUDINAL_ACTIVE,
  tesla_ap_control_state,
)


def test_tesla_ap_control_state_requires_stock_longitudinal_and_ap_flags():
  assert tesla_ap_control_state(STOCK_LONGITUDINAL_ACTIVE, True) == (False, False)
  assert tesla_ap_control_state(AP_HYBRID_ACTIVE, True) == (False, False)
  assert tesla_ap_control_state(STOCK_LONGITUDINAL_ACTIVE | AP_HYBRID_ACTIVE, True) == (True, False)


def test_tesla_ap_lateral_state_and_non_tesla_guard():
  flags = STOCK_LONGITUDINAL_ACTIVE | AP_HYBRID_ACTIVE | AP_HYBRID_STOCK_LATERAL_ACTIVE
  assert tesla_ap_control_state(flags, True) == (True, True)
  assert tesla_ap_control_state(flags, False) == (False, False)
