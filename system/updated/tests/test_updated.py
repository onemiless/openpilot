import fcntl

import pytest

from openpilot.common.params import Params
from openpilot.system.updated import updated
from openpilot.system.updated.updated import Updater


def test_second_updater_instance_exits_cleanly_when_overlay_is_locked(tmp_path):
  lock_file = tmp_path / "safe_staging_overlay.lock"
  with lock_file.open("w") as lock_holder:
    fcntl.flock(lock_holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert updated.acquire_overlay_lock(lock_file) is None


@pytest.mark.parametrize(("device_type", "branch", "expected"), [
  ("tizi", "release3", "release-tizi"),
  ("tizi", "release3-staging", "release-tizi-staging"),
  ("mici", "release3", "release-mici"),
  ("mici", "release3-staging", "release-mici-staging"),
])
def test_target_branch_migration_from_current_branch(mocker, device_type, branch, expected):
  params = Params()
  params.remove("UpdaterTargetBranch")

  mocker.patch("openpilot.system.updated.updated.HARDWARE.get_device_type", return_value=device_type)
  mocker.patch.object(Updater, "get_branch", return_value=branch)

  assert Updater().target_branch == expected


@pytest.mark.parametrize(("device_type", "branch", "expected"), [
  ("tizi", "release3", "release-tizi"),
  ("tizi", "release3-staging", "release-tizi-staging"),
  ("mici", "release3", "release-mici"),
  ("mici", "release3-staging", "release-mici-staging"),
])
def test_target_branch_migration_from_param(mocker, device_type, branch, expected):
  params = Params()
  params.put("UpdaterTargetBranch", branch, block=True)

  mocker.patch("openpilot.system.updated.updated.HARDWARE.get_device_type", return_value=device_type)

  try:
    assert Updater().target_branch == expected
  finally:
    params.remove("UpdaterTargetBranch")
