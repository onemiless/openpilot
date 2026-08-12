from opendbc.car.interfaces import CarInterfaceBase
from opendbc.car.tesla import interface as tesla_interface
from opendbc.car.tesla.values import CAR, TeslaFlags, TeslaSafetyFlags


class FakeParams:
  def __init__(self, *, tools=False, speed_sync=False, speed_from_pcm=0):
    self.values = {
      "EnableTeslaTools": tools,
      "TeslaSpeedSyncEnabled": speed_sync,
      "SpeedFromPCM": speed_from_pcm,
      "TeslaRadarMode": 0,
    }

  def get_bool(self, key):
    return bool(self.values.get(key, False))

  def get_int(self, key):
    return int(self.values.get(key, 0))


def get_tesla_params(monkeypatch, *, alpha_long, tools=False, speed_sync=False, speed_from_pcm=0):
  fake = FakeParams(tools=tools, speed_sync=speed_sync, speed_from_pcm=speed_from_pcm)
  monkeypatch.setattr(tesla_interface, "Params", lambda: fake)
  ret = CarInterfaceBase.get_std_params(CAR.TESLA_MODEL_3)
  return tesla_interface.CarInterface._get_params(ret, CAR.TESLA_MODEL_3, {}, [], alpha_long, False, False)


def test_automatic_turn_signal_is_default_on_and_web_test_is_independent(monkeypatch):
  disabled = get_tesla_params(monkeypatch, alpha_long=True)
  assert not disabled.flags & TeslaFlags.TURN_SIGNAL_TEST
  assert disabled.flags & TeslaFlags.AUTO_TURN_SIGNAL
  assert disabled.safetyConfigs[0].safetyParam & TeslaSafetyFlags.TURN_SIGNAL_TEST

  enabled = get_tesla_params(monkeypatch, alpha_long=False, tools=True)
  assert enabled.flags & TeslaFlags.TURN_SIGNAL_TEST
  assert enabled.flags & TeslaFlags.AUTO_TURN_SIGNAL
  assert enabled.safetyConfigs[0].safetyParam & TeslaSafetyFlags.TURN_SIGNAL_TEST


def test_tesla_longitudinal_remains_disabled_without_alpha_long(monkeypatch):
  disabled = get_tesla_params(monkeypatch, alpha_long=False)

  assert not disabled.openpilotLongitudinalControl
  assert not disabled.safetyConfigs[0].safetyParam & TeslaSafetyFlags.LONG_CONTROL
  assert disabled.safetyConfigs[0].safetyParam & TeslaSafetyFlags.TURN_SIGNAL_TEST


def test_speed_sync_is_disabled_pending_vehicle_capture(monkeypatch):
  no_pcm = get_tesla_params(monkeypatch, alpha_long=True, speed_sync=True, speed_from_pcm=0)
  assert not no_pcm.flags & TeslaFlags.SPEED_SYNC

  no_long = get_tesla_params(monkeypatch, alpha_long=False, speed_sync=True, speed_from_pcm=1)
  assert not no_long.flags & TeslaFlags.SPEED_SYNC

  requested = get_tesla_params(monkeypatch, alpha_long=True, speed_sync=True, speed_from_pcm=1)
  assert not requested.flags & TeslaFlags.SPEED_SYNC
  assert not requested.safetyConfigs[0].safetyParam & TeslaSafetyFlags.SPEED_SYNC
