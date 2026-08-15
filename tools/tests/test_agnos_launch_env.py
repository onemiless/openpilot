import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).parents[2]
MANIFEST = ROOT / "openpilot/common/hardware/tici/agnos-19.6.json"
MANIFEST_SHA256 = "5981fa796c96083d8ff38b2102a4c3580b2fd596e81f6d3c76cb096231c5ffb5"


def read_target(approval_file: Path) -> tuple[str, str]:
  env = os.environ | {"SP_AGNOS_APPROVAL_FILE": str(approval_file)}
  output = subprocess.check_output(
    ["bash", "-c", "unset AGNOS_VERSION AGNOS_MANIFEST_REL; source launch_env.sh; printf '%s\\n%s' \"$AGNOS_VERSION\" \"$AGNOS_MANIFEST_REL\""],
    cwd=ROOT,
    env=env,
    text=True,
  )
  version, manifest = output.splitlines()
  return version, manifest


def test_default_stays_on_18_5(tmp_path: Path) -> None:
  assert read_target(tmp_path / "missing") == ("18.5", "openpilot/system/hardware/tici/agnos.json")


def test_wrong_approval_stays_on_18_5(tmp_path: Path) -> None:
  approval = tmp_path / "approval"
  approval.write_text("0" * 64)
  assert read_target(approval) == ("18.5", "openpilot/system/hardware/tici/agnos.json")


def test_exact_approval_selects_19_6(tmp_path: Path) -> None:
  approval = tmp_path / "approval"
  approval.write_text(f"{MANIFEST_SHA256}\n")
  assert MANIFEST.exists()
  assert read_target(approval) == ("19.6", "openpilot/common/hardware/tici/agnos-19.6.json")
