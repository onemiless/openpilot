import subprocess
from pathlib import Path

from openpilot.system.updated import updated


class FakeWaitHelper:
  def __init__(self):
    self.sleeps = []

  def sleep(self, seconds):
    self.sleeps.append(seconds)


class FakeParams:
  def __init__(self):
    self.values = {}

  def put(self, key, value, **kwargs):
    self.values[key] = value


def test_mihomo_proxy_missing_config_does_not_start(mocker, tmp_path: Path):
  mocker.patch.object(updated, "MIHOMO_CONFIG", tmp_path / "missing-config.yaml")
  mocker.patch.object(updated, "MIHOMO_CONTROL", tmp_path / "mihomo_control.py")
  run = mocker.patch("subprocess.run")

  assert updated.get_mihomo_proxy_env() is None
  run.assert_not_called()


def test_mihomo_proxy_env_starts_and_verifies_listener(mocker, tmp_path: Path):
  config = tmp_path / "config.yaml"
  control = tmp_path / "mihomo_control.py"
  config.touch()
  control.touch()
  mocker.patch.object(updated, "MIHOMO_CONFIG", config)
  mocker.patch.object(updated, "MIHOMO_CONTROL", control)
  mocker.patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0, "mihomo started", ""))
  connection = mocker.patch("socket.create_connection")
  connection.return_value.__enter__.return_value = mocker.Mock()

  env = updated.get_mihomo_proxy_env()

  assert env is not None
  assert env["https_proxy"] == "http://127.0.0.1:7890"
  assert env["ALL_PROXY"] == "http://127.0.0.1:7890"
  connection.assert_called_once_with(("127.0.0.1", 7890), timeout=2)


def test_mihomo_proxy_falls_back_when_listener_is_unavailable(mocker, tmp_path: Path):
  config = tmp_path / "config.yaml"
  control = tmp_path / "mihomo_control.py"
  config.touch()
  control.touch()
  mocker.patch.object(updated, "MIHOMO_CONFIG", config)
  mocker.patch.object(updated, "MIHOMO_CONTROL", control)
  mocker.patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0, "mihomo started", ""))
  mocker.patch("socket.create_connection", side_effect=OSError("not listening"))

  assert updated.get_mihomo_proxy_env() is None


def test_updater_check_passes_proxy_env_to_remote_git_commands(mocker):
  proxy_env = {"https_proxy": "http://127.0.0.1:7890"}
  mocker.patch.object(updated, "get_mihomo_proxy_env", return_value=proxy_env)
  mocker.patch.object(updated.Updater, "get_branch", return_value="dev")
  mocker.patch.object(updated.Updater, "get_commit_hash", return_value="abc123")
  run = mocker.patch.object(updated, "run", return_value="abc123\trefs/heads/dev\n")

  updater = updated.Updater()
  updater.params.put("UpdaterTargetBranch", "dev")
  try:
    updater.check_for_update()
  finally:
    updater.params.remove("UpdaterTargetBranch")

  remote_calls = [call for call in run.call_args_list if "ls-remote" in call.args[0]]
  assert len(remote_calls) == 2
  assert all(call.kwargs["env"] == proxy_env for call in remote_calls)


def test_invalid_system_time_publishes_waiting_state(mocker):
  params = FakeParams()
  wait_helper = FakeWaitHelper()
  mocker.patch.object(updated, "system_time_valid", return_value=False)

  assert not updated.update_check_time_ready(params, wait_helper, first_run=False)
  assert params.values["UpdaterState"] == updated.UPDATER_WAITING_FOR_TIME_STATE
  assert wait_helper.sleeps == [60]


def test_valid_system_time_allows_check_after_first_run(mocker):
  params = FakeParams()
  wait_helper = FakeWaitHelper()
  mocker.patch.object(updated, "system_time_valid", return_value=True)

  assert updated.update_check_time_ready(params, wait_helper, first_run=False)
  assert wait_helper.sleeps == []
