from __future__ import annotations

import subprocess

import pytest

from openpilot.selfdrive.debug.device_hotspot import (
  LOCAL_HOTSPOT_URL,
  TESLA_HOTSPOT_URL,
  hotspot_status,
  set_tesla_address_enabled,
  tesla_address_ready,
)
from openpilot.selfdrive.debug.tesla_hotspotd import TeslaHotspotAddressManager


class FakeRunner:
  def __init__(self, *, hotspot_active: bool, address_ready: bool = False, nmcli_available: bool = True):
    self.hotspot_active = hotspot_active
    self.address_ready = address_ready
    self.nmcli_available = nmcli_available
    self.commands: list[list[str]] = []

  def __call__(self, command: list[str], **kwargs) -> subprocess.CompletedProcess:
    del kwargs
    self.commands.append(command)
    if "nmcli" in command:
      stdout = "Hotspot:wlan0\n" if self.hotspot_active else ""
      return subprocess.CompletedProcess(command, 0 if self.nmcli_available else 1, stdout, "")
    if command[:5] == ["ip", "-o", "-4", "address", "show"]:
      stdout = "1: lo    inet 99.99.99.99/32 scope global lo\n" if self.address_ready else ""
      return subprocess.CompletedProcess(command, 0, stdout, "")
    if command[:5] == ["sudo", "-n", "ip", "address", "replace"]:
      self.address_ready = True
      return subprocess.CompletedProcess(command, 0, "", "")
    if command[:5] == ["sudo", "-n", "ip", "address", "delete"]:
      self.address_ready = False
      return subprocess.CompletedProcess(command, 0, "", "")
    raise AssertionError(f"unexpected command: {command}")


def test_hotspot_status_exposes_both_access_urls_and_address_readiness():
  runner = FakeRunner(hotspot_active=True, address_ready=True)

  status = hotspot_status(runner)

  assert status == {
    "available": True,
    "active": True,
    "connection": "Hotspot",
    "url": LOCAL_HOTSPOT_URL,
    "tesla_url": TESLA_HOTSPOT_URL,
    "tesla_address_ready": True,
  }


def test_address_helpers_are_idempotent():
  runner = FakeRunner(hotspot_active=True)

  assert not tesla_address_ready(runner)
  assert set_tesla_address_enabled(True, runner)
  assert set_tesla_address_enabled(True, runner)
  assert not set_tesla_address_enabled(False, runner)

  mutations = [command for command in runner.commands if command[:3] == ["sudo", "-n", "ip"]]
  assert [command[4] for command in mutations] == ["replace", "delete"]


def test_manager_adds_address_while_hotspot_is_active():
  runner = FakeRunner(hotspot_active=True)

  assert TeslaHotspotAddressManager(runner).reconcile()
  assert runner.address_ready


def test_manager_removes_stale_address_after_hotspot_stops():
  runner = FakeRunner(hotspot_active=False, address_ready=True)

  assert not TeslaHotspotAddressManager(runner).reconcile()
  assert not runner.address_ready


def test_manager_preserves_address_when_networkmanager_state_is_unavailable():
  runner = FakeRunner(hotspot_active=False, address_ready=True, nmcli_available=False)

  with pytest.raises(RuntimeError, match="NetworkManager"):
    TeslaHotspotAddressManager(runner).reconcile()

  assert runner.address_ready


def test_manager_close_removes_owned_address():
  runner = FakeRunner(hotspot_active=True, address_ready=True)
  manager = TeslaHotspotAddressManager(runner)

  manager.close()

  assert not runner.address_ready
  assert not manager.address_enabled
