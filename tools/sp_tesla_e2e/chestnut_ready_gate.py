#!/usr/bin/env python3
"""Failure cases: premature GPU load, missing USB, non-L0/unreadable link,
missed deadline, or probing PCIe before USB enumeration. No hardware access.
Run before real-camera E2E; emit a repeatable JSON gate artifact.
"""
import ast
import json
from pathlib import Path
from types import SimpleNamespace

root = Path(__file__).resolve().parents[2]
source = ast.parse((root / "openpilot/selfdrive/modeld/helpers.py").read_text())
function = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == "wait_for_chestnut")
results = []
for name, usb_at, link_at, expected in (
  ("ready", 0., 0., "ready"),
  ("delayed_link", 0., .5, "ready"),
  ("delayed_usb", .3, .5, "ready"),
  ("missing_usb", 9., 9., "timeout"),
  ("non_l0", 0., 9., "timeout"),
  ("unreadable", 0., None, "timeout"),
):
  clock = [0.]
  probes = []
  def sleep(seconds, clock=clock):
    clock[0] += seconds
  def link_up(clock=clock, usb_at=usb_at, probes=probes, link_at=link_at):
    assert clock[0] >= usb_at, "PCIe probe before enumeration"
    probes.append(clock[0])
    return None if link_at is None else clock[0] >= link_at
  scope = {"time": SimpleNamespace(monotonic=lambda clock=clock: clock[0], sleep=sleep),
           "chestnut_present": lambda clock=clock, usb_at=usb_at: clock[0] >= usb_at, "link_up": link_up}
  exec(compile(ast.Module(body=[function], type_ignores=[]), "helpers.py", "exec"), scope)
  try:
    scope["wait_for_chestnut"](timeout=1.)
    actual = "ready"
  except TimeoutError:
    actual = "timeout"
  passed = actual == expected and (actual != "ready" or link_at is not None and clock[0] >= link_at) and clock[0] <= 1.11
  results.append({"case": name, "passed": passed, "result": actual, "seconds": round(clock[0], 2), "probes": len(probes)})
print(json.dumps(results, indent=2))
assert all(r["passed"] for r in results)
