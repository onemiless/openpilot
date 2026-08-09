from openpilot.sunnypilot import gps_time_sync


class FakeParams:
  def __init__(self, values):
    self.values = values

  def get_bool(self, key):
    return self.values.get(key, False)


def test_initial_gps_sync_uses_shared_system_time_validity(mocker):
  params = FakeParams({"IsOffroad": True, "GpsTimeSyncDone": False})
  mocker.patch.object(gps_time_sync, "system_time_valid", return_value=False)

  assert gps_time_sync.should_wait_for_initial_fix(params)


def test_initial_gps_sync_skips_valid_clock(mocker):
  params = FakeParams({"IsOffroad": True, "GpsTimeSyncDone": False})
  mocker.patch.object(gps_time_sync, "system_time_valid", return_value=True)

  assert not gps_time_sync.should_wait_for_initial_fix(params)
