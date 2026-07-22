from types import SimpleNamespace

from openpilot.selfdrive.car.card import get_tesla_longitudinal_context


class FakeSubMaster:
  def __init__(self):
    self.updated = {"longitudinalPlanSP": True}
    self.valid = {"longitudinalPlanSP": True, "carControl": True}
    self.seen = {"longitudinalPlanSP": True, "carControl": True}
    self.recv_time = {"longitudinalPlanSP": 10.0, "carControl": 10.0}
    self.data = {
      "longitudinalPlanSP": SimpleNamespace(longitudinalPlanSource=SimpleNamespace(raw=1)),
      "carControl": SimpleNamespace(leftBlinker=True, rightBlinker=False),
    }

  def __getitem__(self, key):
    return self.data[key]


def test_tesla_longitudinal_context_uses_new_plan_and_lane_change_state():
  context = get_tesla_longitudinal_context(FakeSubMaster(), 10.05)

  assert context == (1, True, True, 10.0, True, True, 10.05)


def test_tesla_longitudinal_context_rejects_stale_messages():
  sm = FakeSubMaster()
  sm.updated["longitudinalPlanSP"] = False
  sm.recv_time["longitudinalPlanSP"] = 9.7
  sm.recv_time["carControl"] = 9.7

  context = get_tesla_longitudinal_context(sm, 10.05)

  assert context == (1, False, False, 9.7, True, False, 10.05)
