"""Exercise the prebuilt startup policy without target-only native libraries."""
import ast
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from openpilot.sunnypilot.hardware.profile import has_driver_camera

ROOT = Path(__file__).resolve().parents[4]


@pytest.mark.parametrize("profile", ["standard", "c3xl"])
@pytest.mark.parametrize("started", [False, True])
@pytest.mark.parametrize("preview", [False, True])
def test_monitoring_never_requested(profile, started, preview, monkeypatch):
  monkeypatch.setenv("SUNNYPILOT_HARDWARE_PROFILE", profile)
  source = ROOT / "openpilot/system/manager/process_config.py"
  tree = ast.parse(source.read_text())
  functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ("driverview", "visual_driver_monitoring")]
  # Execute actual process predicates, substituting only Params and CarParams.
  namespace = {"has_driver_camera": has_driver_camera, "Params": object, "car": SimpleNamespace(CarParams=object)}
  exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), "exec"), namespace)
  params = SimpleNamespace(get_bool=lambda key: preview)
  assert not namespace["visual_driver_monitoring"](started, params, object())


def test_launcher_disables_native_cabin_stream():
  env = dict(os.environ, DISABLE_DRIVER="0", SUNNYPILOT_HARDWARE_PROFILE="standard")
  subprocess.check_call(["bash", "-c", 'source "$1"; test "$DISABLE_DRIVER" = 1', "bash", str(ROOT / "launch_env.sh")], env=env)


def test_dm_disabled_keeps_longitudinal_events():
  source = ROOT / "openpilot/selfdrive/selfdrived/selfdrived.py"
  tree = ast.parse(source.read_text())
  cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SelfdriveD")
  method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "update_events")
  dm_index = next(i for i, n in enumerate(method.body) if isinstance(n, ast.If) and "has_driver_camera()" in ast.unparse(n.test))
  events = []
  state = SimpleNamespace(CP=SimpleNamespace(notCar=False), sm={"longitudinalPlanSP": SimpleNamespace(events=["planner-event"])},
                          events_sp=SimpleNamespace(add_from_msg=events.extend))
  # No driverMonitoringState exists. Disabled DM must not read it or drop planner events.
  exec(compile(ast.Module(body=method.body[dm_index:dm_index + 2], type_ignores=[]), str(source), "exec"),
       {"self": state, "has_driver_camera": has_driver_camera})
  assert events == ["planner-event"]
