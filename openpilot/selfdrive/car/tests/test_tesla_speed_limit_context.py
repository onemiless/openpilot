from types import SimpleNamespace

from openpilot.selfdrive.car.card import get_tesla_speed_limit_context


def make_plan(*, assist_enabled: bool):
  resolver = SimpleNamespace(
    speedLimitValid=True,
    speedLimitLastValid=False,
    speedLimitFinalLast=25.0,
  )
  return SimpleNamespace(
    speedLimit=SimpleNamespace(
      resolver=resolver,
      assist=SimpleNamespace(enabled=assist_enabled),
    ),
  )


class FakeSubMaster:
  def __init__(self, assist_enabled: bool, recv_time: float = 10.0):
    self.plan = make_plan(assist_enabled=assist_enabled)
    self.seen = {"longitudinalPlanSP": True}
    self.valid = {"longitudinalPlanSP": True}
    self.recv_time = {"longitudinalPlanSP": recv_time}

  def __getitem__(self, service):
    assert service == "longitudinalPlanSP"
    return self.plan


def test_tesla_speed_limit_target_requires_assist_mode():
  target, valid, _ = get_tesla_speed_limit_context(FakeSubMaster(assist_enabled=False), now=10.1)
  assert target == 0.0
  assert not valid

  target, valid, _ = get_tesla_speed_limit_context(FakeSubMaster(assist_enabled=True), now=10.1)
  assert target == 25.0
  assert valid


def test_tesla_speed_limit_target_rejects_stale_plan():
  target, valid, _ = get_tesla_speed_limit_context(FakeSubMaster(assist_enabled=True), now=10.3)
  assert target == 0.0
  assert not valid
