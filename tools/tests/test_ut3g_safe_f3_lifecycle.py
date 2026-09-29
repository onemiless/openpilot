import sys
from unittest.mock import Mock

import pytest

from tools import ut3g_safe_f3_poweroff as poweroff


class FakeUSB:
  def __init__(self, after=0):
    self.product = poweroff.PRODUCT
    self.values = [poweroff.PCIE_L0, after]
    self.read_count = 0
    self.writes = []

  def control_read(self, request, length, **kwargs):
    assert (request, length) == (0xE4, 1)
    self.read_count += 1
    return bytes((self.values.pop(0) if len(self.values) > 1 else self.values[0],))

  def control_write(self, request, **kwargs):
    self.writes.append((request, kwargs))


def test_wait_for_gpu_users_runs_only_while_offroad(tmp_path, monkeypatch):
  offroad = tmp_path / "IsOffroad"
  offroad.write_bytes(b"1")
  conflicts = Mock(side_effect=[[{"pid": 123, "command": "modeld"}], []])
  sleeper = Mock()
  monkeypatch.setattr(poweroff, "conflicting_processes", conflicts)

  poweroff.wait_for_gpu_users(offroad_path=offroad, sleeper=sleeper)

  assert conflicts.call_count == 2
  sleeper.assert_called_once_with(0.1)


def test_wait_for_gpu_users_aborts_when_onroad_resumes(tmp_path, monkeypatch):
  offroad = tmp_path / "IsOffroad"
  offroad.write_bytes(b"1")
  monkeypatch.setattr(poweroff, "conflicting_processes",
                     lambda proc_root: [{"pid": 123, "command": "modeld"}])

  def resume_onroad(_seconds):
    offroad.write_bytes(b"0")

  with pytest.raises(poweroff.SafePowerOffError, match="not confirmed offroad"):
    poweroff.wait_for_gpu_users(offroad_path=offroad, sleeper=resume_onroad)


def test_manual_poweroff_keeps_four_sample_verification():
  usb = FakeUSB()
  sleeper = Mock()

  report = poweroff.safe_power_off(usb, sleeper=sleeper)

  assert usb.read_count == 5
  assert sleeper.call_count == 3
  assert report["ltssm_samples"] == [0, 0, 0, 0]
  assert report["verification_seconds"] == 3


def test_fast_release_uses_one_immediate_verification():
  usb = FakeUSB()
  sleeper = Mock()

  report = poweroff.safe_power_off(usb, sleeper=sleeper, post_f3_samples=1)

  assert usb.read_count == 2
  sleeper.assert_not_called()
  assert report["ltssm_samples"] == [0]
  assert report["verification_seconds"] == 0


def test_fast_release_cli_requires_wait_for_users(monkeypatch, capsys):
  monkeypatch.setattr(sys, "argv", ["ut3g_safe_f3_poweroff.py", "--fast-release-after-f3"])

  with pytest.raises(SystemExit) as exc:
    poweroff.main()

  assert exc.value.code == 2
  assert "--fast-release-after-f3 requires --wait-for-users" in capsys.readouterr().err


def test_fast_release_cli_accepts_automatic_pair(monkeypatch):
  monkeypatch.setattr(sys, "argv", [
    "ut3g_safe_f3_poweroff.py", "--wait-for-users", "--fast-release-after-f3",
  ])
  monkeypatch.setattr(poweroff.os, "geteuid", lambda: 1, raising=False)

  with pytest.raises(poweroff.SafePowerOffError, match="run as root"):
    poweroff.main()


def test_final_offroad_user_check_prevents_f3_write():
  usb = FakeUSB()

  def reject():
    raise poweroff.SafePowerOffError("GPU users started before F3 poweroff")

  with pytest.raises(poweroff.SafePowerOffError, match="GPU users started"):
    poweroff.safe_power_off(usb, before_f3=reject)

  assert usb.writes == []
