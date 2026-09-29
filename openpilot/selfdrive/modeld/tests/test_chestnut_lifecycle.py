"""Keep Chestnut shutdown outside both modeld process exit paths."""
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest


ROOT = Path(__file__).resolve().parents[3]
ENTRIES = ("selfdrive/modeld/modeld.py", "sunnypilot/modeld_v2/modeld.py")


@pytest.mark.parametrize("entry", ENTRIES, ids=("legacy", "v2"))
def test_modeld_exit_path_does_not_power_down_chestnut(entry):
  path = ROOT / entry
  tree = ast.parse(path.read_text(encoding="utf-8"))
  functions = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}

  assert "main" in functions
  assert "_main" not in functions
  assert not any(
    (isinstance(node, ast.Name) and node.id == "link_down") or
    (isinstance(node, ast.Attribute) and node.attr == "link_down")
    for node in ast.walk(tree)
  )


@pytest.mark.parametrize("entry", ENTRIES, ids=("legacy", "v2"))
def test_big_model_path_preloads_and_warms_the_small_fallback(entry):
  tree = ast.parse((ROOT / entry).read_text(encoding="utf-8"))
  calls = {ast.unparse(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}
  assignments = {
    (ast.unparse(target), ast.unparse(node.value))
    for node in ast.walk(tree) if isinstance(node, ast.Assign)
    for target in node.targets
  }

  assert "preloaded_small_model.warmup" in calls
  assert ("small_model", "preloaded_small_model") in assignments


@pytest.mark.parametrize("entry", ENTRIES, ids=("legacy", "v2"))
def test_missing_small_fallback_raises_an_explicit_runtime_error(entry):
  tree = ast.parse((ROOT / entry).read_text(encoding="utf-8"))
  guarded_raises = [
    node for node in ast.walk(tree)
    if isinstance(node, ast.If)
    and ast.unparse(node.test) == "small_model is None"
    and any(
      isinstance(child, ast.Raise)
      and isinstance(child.exc, ast.Call)
      and ast.unparse(child.exc.func) == "RuntimeError"
      and child.cause is not None
      for child in node.body
    )
  ]

  assert guarded_raises


@pytest.fixture
def asm_transport():
  path = ROOT.parent / "tinygrad_repo/tinygrad/runtime/support/usb.py"
  tree = ast.parse(path.read_text(encoding="utf-8"))
  node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "CustomASM24Controller")
  node.body = [n for n in node.body if isinstance(n, ast.FunctionDef) and n.name in ("__init__", "set_pcie_power")]
  environment = {"USB3": object}
  exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), environment)
  controller = environment["CustomASM24Controller"]
  controller.read = Mock()
  return controller, SimpleNamespace(control_write=Mock())


def test_existing_l0_link_is_not_powered_on_again(asm_transport):
  controller, usb = asm_transport
  controller.read.side_effect = (b"\x78", b"\x78")

  controller(usb)

  assert controller.read.call_args_list == [call(0xB450, 1), call(0xB450, 1)]
  usb.control_write.assert_not_called()


def test_powered_down_link_is_woken_once_and_verified(asm_transport):
  controller, usb = asm_transport
  controller.read.side_effect = (b"\x00", b"\x78")

  controller(usb)

  usb.control_write.assert_called_once_with(0xF3, value=1, timeout=10000)
  assert controller.read.call_args_list == [call(0xB450, 1), call(0xB450, 1)]


def test_link_that_does_not_wake_still_fails_initialization(asm_transport):
  controller, usb = asm_transport
  controller.read.side_effect = (b"\x00", b"\x00")

  with pytest.raises(RuntimeError, match="PCIe link not up.*LTSSM=0x00"):
    controller(usb)

  usb.control_write.assert_called_once_with(0xF3, value=1, timeout=10000)
  assert controller.read.call_args_list == [call(0xB450, 1), call(0xB450, 1)]
