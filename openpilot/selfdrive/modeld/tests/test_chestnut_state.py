"""Exercise production telemetry without opening a GPU or native message sockets."""
import ast
from functools import cached_property
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


MODELD = Path(__file__).resolve().parents[1] / "modeld.py"


@pytest.fixture
def telemetry():
  messages = []
  device = Mock()
  device._opened_devices = {"AMD"}
  device.__getitem__ = Mock(return_value=SimpleNamespace(iface=SimpleNamespace(
    pci_dev=SimpleNamespace(usb=object()), dev_impl=SimpleNamespace(vram_size=8 << 30),
  )))
  read = Mock(return_value=SimpleNamespace(
    link_valid=True, pcie_ltssm=0x78, supply_valid=True, supply_voltage_mv=12000, supply_current_ma=5000,
  ))
  environment = {
    "PubMaster": object, "cached_property": cached_property, "Device": device,
    "GlobalCounters": SimpleNamespace(mem_used_per_device={"AMD": 1 << 30}),
    "messaging": SimpleNamespace(new_message=lambda _: SimpleNamespace(chestnutState=SimpleNamespace())),
    "read_runtime_asm_telemetry": read,
  }
  tree = ast.parse(MODELD.read_text(encoding="utf-8"))
  node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ChestnutState")
  exec(compile(ast.Module(body=[node], type_ignores=[]), str(MODELD), "exec"), environment)
  state = environment["ChestnutState"](SimpleNamespace(send=lambda _service, msg: messages.append(msg)), True)
  # Exercise runtime link reads between the existing, independent SMU refreshes.
  state.sends = 1
  return state, device, read, messages


def test_big_model_retains_live_telemetry(telemetry):
  state, device, read, messages = telemetry

  state.send()

  read.assert_called_once_with(device.__getitem__.return_value.iface.pci_dev.usb)
  assert messages[0].valid
  assert messages[0].chestnutState.pcieLtssm == 0x78
  assert messages[0].chestnutState.supplyValid
  assert messages[0].chestnutState.supplyVoltage == 12000
  assert messages[0].chestnutState.supplyCurrent == 5000
  assert messages[0].chestnutState.memoryUsedMb == 1024
  assert messages[0].chestnutState.memoryTotalMb == 8192


@pytest.mark.parametrize("opened", [True, False])
def test_small_model_never_accesses_amd_but_keeps_publishing(telemetry, opened):
  state, device, read, messages = telemetry
  state.big = False
  device._opened_devices = {"AMD"} if opened else set()
  device.__getitem__.side_effect = AssertionError("fallback must not access the failed GPU")

  for _ in range(25):
    state.send()

  device.__getitem__.assert_not_called()
  read.assert_not_called()
  assert len(messages) == 25
  assert all(not message.valid for message in messages)


def test_runtime_fallback_stops_usb_reads_and_invalidates_old_telemetry(telemetry):
  state, device, read, messages = telemetry
  state.send()
  assert messages[-1].valid

  state.big = False
  device.__getitem__.reset_mock()
  device.__getitem__.side_effect = AssertionError("USB transport failed")
  state.send()

  device.__getitem__.assert_not_called()
  assert read.call_count == 1
  assert len(messages) == 2
  assert not messages[-1].valid


def test_unopened_amd_is_not_initialized_for_telemetry(telemetry):
  state, device, read, messages = telemetry
  device._opened_devices = set()

  state.send()

  device.__getitem__.assert_not_called()
  read.assert_not_called()
  assert not messages[0].valid
