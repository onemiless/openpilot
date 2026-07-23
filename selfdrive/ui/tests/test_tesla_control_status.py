from openpilot.selfdrive.ui.sunnypilot.onroad.smart_cruise_control import tesla_ap_control_state


def test_tesla_ap_control_state_requires_ap_stock_longitudinal():
  assert tesla_ap_control_state(0, True) == (False, False)
  assert tesla_ap_control_state(512, True) == (False, False)
  assert tesla_ap_control_state(32, True) == (False, False)
  assert tesla_ap_control_state(32 | 512, True) == (True, False)


def test_tesla_ap_control_state_distinguishes_full_ap_control():
  assert tesla_ap_control_state(32 | 512 | 8192, True) == (True, True)


def test_tesla_ap_control_state_ignores_other_brands():
  assert tesla_ap_control_state(32 | 512 | 8192, False) == (False, False)
