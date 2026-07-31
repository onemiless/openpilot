from types import SimpleNamespace

from openpilot.selfdrive.car.card import get_tesla_longitudinal_context, get_tesla_speed_limit_context


class FakeSubMaster:
  def __init__(self):
    self.updated = {"longitudinalPlanSP": True}
    self.valid = {"longitudinalPlanSP": True, "carControl": True, "selfdriveStateSP": True}
    self.seen = {"longitudinalPlanSP": True, "carControl": True, "selfdriveStateSP": True}
    self.recv_time = {"longitudinalPlanSP": 10.0, "carControl": 10.0, "selfdriveStateSP": 10.0}
    self.data = {
      "longitudinalPlanSP": SimpleNamespace(
        longitudinalPlanSource=SimpleNamespace(raw=1),
        speedLimit=SimpleNamespace(resolver=SimpleNamespace(
          speedLimitValid=True, speedLimitLastValid=False, speedLimitFinalLast=25.0,
        )),
      ),
      "carControl": SimpleNamespace(leftBlinker=True, rightBlinker=False, latActive=True, longActive=True,
                                    actuators=SimpleNamespace(accel=-0.25)),
      "selfdriveStateSP": SimpleNamespace(mads=SimpleNamespace(active=True)),
    }

  def __getitem__(self, key):
    return self.data[key]


def test_tesla_longitudinal_context_uses_new_plan_and_lane_change_state():
  context = get_tesla_longitudinal_context(FakeSubMaster(), 10.05)

  assert context == (1, True, True, 10.0, True, True, True, 10.05, True, -0.25, True)


def test_tesla_longitudinal_context_rejects_stale_messages():
  sm = FakeSubMaster()
  sm.updated["longitudinalPlanSP"] = False
  sm.recv_time["longitudinalPlanSP"] = 9.7
  sm.recv_time["carControl"] = 9.7
  sm.recv_time["selfdriveStateSP"] = 9.7

  context = get_tesla_longitudinal_context(sm, 10.05)

  assert context == (1, False, False, 9.7, True, False, False, 10.05, True, -0.25, False)


def test_tesla_longitudinal_context_accepts_active_mads_at_standstill():
  sm = FakeSubMaster()
  sm.data["carControl"].latActive = False

  context = get_tesla_longitudinal_context(sm, 10.05)

  assert context[6]


def test_tesla_speed_limit_context_uses_final_limit_with_configured_offset():
  context = get_tesla_speed_limit_context(FakeSubMaster(), 10.05)

  assert context == (25.0, True, 10.0)


def test_tesla_speed_limit_context_rejects_stale_or_missing_limit():
  sm = FakeSubMaster()
  sm.recv_time["longitudinalPlanSP"] = 9.7
  assert get_tesla_speed_limit_context(sm, 10.05) == (0.0, False, 9.7)

  sm.recv_time["longitudinalPlanSP"] = 10.0
  sm.data["longitudinalPlanSP"].speedLimit.resolver.speedLimitValid = False
  sm.data["longitudinalPlanSP"].speedLimit.resolver.speedLimitLastValid = False
  assert get_tesla_speed_limit_context(sm, 10.05) == (0.0, False, 10.0)
