import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).parents[2]


def read_target(approval_file: Path) -> str:
  env = os.environ | {"SP_AGNOS_APPROVAL_FILE": str(approval_file)}
  return subprocess.check_output(
    ["bash", "-c", "unset AGNOS_VERSION; source launch_env.sh; printf '%s' \"$AGNOS_VERSION\""],
    cwd=ROOT,
    env=env,
    text=True,
  )


def test_default_stays_on_18_5(tmp_path: Path) -> None:
  assert read_target(tmp_path / "missing") == "18.5"


def test_old_19_6_approval_marker_is_ignored(tmp_path: Path) -> None:
  approval = tmp_path / "approval"
  approval.write_text("5981fa796c96083d8ff38b2102a4c3580b2fd596e81f6d3c76cb096231c5ffb5\n")
  assert read_target(approval) == "18.5"
