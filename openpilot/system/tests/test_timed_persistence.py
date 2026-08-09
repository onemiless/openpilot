import datetime

from openpilot.system import timed


class FakeParams:
  def __init__(self, values=None):
    self.values = values or {}
    self.put_calls = []

  def get(self, key, **kwargs):
    return self.values.get(key)

  def put(self, key, value, **kwargs):
    self.values[key] = value
    self.put_calls.append((key, value, kwargs))


def test_set_time_uses_sudo_date(mocker):
  new_time = datetime.datetime(2030, 1, 2, 3, 4, 5)
  run = mocker.patch.object(timed.subprocess, "run")

  timed.set_time(new_time)

  run.assert_called_once_with(
    ["sudo", "date", "-u", "-s", "2030-01-02 03:04:05"],
    check=True,
  )


def test_restore_uses_newest_valid_persisted_time(mocker):
  older = datetime.datetime(2026, 8, 8, 12, 0)
  newer = datetime.datetime(2026, 8, 9, 2, 39)
  params = FakeParams({"LastKnownGoodTime": older, "LastUpdateTime": newer})
  mocker.patch.object(timed, "system_time_valid", return_value=False)
  set_time = mocker.patch.object(timed, "set_time")

  assert timed.restore_persisted_time(params)
  set_time.assert_called_once_with(newer)


def test_restore_rejects_invalid_persisted_time(mocker):
  params = FakeParams({"LastKnownGoodTime": datetime.datetime(2024, 1, 1)})
  mocker.patch.object(timed, "system_time_valid", return_value=False)
  set_time = mocker.patch.object(timed, "set_time")

  assert not timed.restore_persisted_time(params)
  set_time.assert_not_called()


def test_persist_known_good_time_is_write_limited(mocker):
  now = datetime.datetime(2026, 8, 9, 6, 0)
  params = FakeParams({"LastKnownGoodTime": now - datetime.timedelta(hours=1)})
  mocker.patch.object(timed, "system_time_valid", return_value=True)

  assert not timed.persist_known_good_time(params, now)
  assert params.put_calls == []

  later = now + timed.LAST_KNOWN_TIME_WRITE_INTERVAL
  assert timed.persist_known_good_time(params, later)
  assert params.put_calls == [("LastKnownGoodTime", later, {"block": False})]
