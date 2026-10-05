#!/usr/bin/env python3
"""Exercise the actual branch dialog/callback locally; no device/update signals."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import uuid
import pyray as rl

os.environ["OPENPILOT_PREFIX"] = "sp-branch-e2e-" + uuid.uuid4().hex[:8]

from openpilot.common.prefix import OpenpilotPrefix
from openpilot.sunnypilot.hardware.profile import HardwareProfile
from openpilot.system.ui.widgets import DialogResult


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--output", type=Path, default=Path("artifacts/sp-tesla-migration/branch-selection.json"))
  args = parser.parse_args()
  available = ["dev-sp", "release-tici", "staging-tici", "master-tici", "release-tici-staging",
               "feature-tici", "dev-sp-egpu", "dev-sp-egpu-nva", "dev-sp-egpu-prebuild", "navassist-track-p0",
               "master", "dev", "release-mici", "dev-sp", "feature-prebuilt"]
  cases = [
    ("standard", HardwareProfile.STANDARD, "dev-sp", available,
     ["dev-sp", "release-tici", "staging-tici", "master-tici", "release-tici-staging"]),
    ("c3xl", HardwareProfile.C3XL, "dev-sp", available,
     ["dev-sp", "dev-sp-egpu", "dev-sp-egpu-nva", "dev-sp-egpu-prebuild", "navassist-track-p0"]),
    ("installed-custom", HardwareProfile.STANDARD, "local-custom", available,
     ["local-custom", "dev-sp", "release-tici", "staging-tici", "master-tici", "release-tici-staging"]),
    ("installed-c3xl-custom", HardwareProfile.C3XL, "local-custom", available,
     ["local-custom", "dev-sp", "dev-sp-egpu", "dev-sp-egpu-nva", "dev-sp-egpu-prebuild", "navassist-track-p0"]),
    ("installed-only", HardwareProfile.C3XL, "dev-sp", [], ["dev-sp"]),
    ("empty-metadata", HardwareProfile.STANDARD, "", [], []),
    ("legacy-c3xl-subset", HardwareProfile.C3XL, "dev-sp",
     ["dev-sp-egpu", "dev-sp-egpu-nva", "dev-sp-egpu-prebuild", "dev", "master-new", "release-tici", "staging-tici"],
     ["dev-sp", "dev-sp-egpu", "dev-sp-egpu-nva", "dev-sp-egpu-prebuild"]),
    ("non-tici-prebuild-spellings", HardwareProfile.STANDARD, "dev-sp", available, list(dict.fromkeys(available))),
  ]
  records = []
  with OpenpilotPrefix(prefix=os.environ["OPENPILOT_PREFIX"]):
    from openpilot.selfdrive.ui.sunnypilot.layouts.settings import software
    for name, profile, current, remote, expected in cases:
      device_type = "tizi" if name == "non-tici-prebuild-spellings" else "tici"
      values = {"GitBranch": current, "UpdaterAvailableBranches": ",".join(remote), "UpdaterTargetBranch": "feature-tici"}
      writes = []
      params = SimpleNamespace(get=values.get, put=lambda key, value, writes=writes: writes.append((key, value)))
      layout = software.SoftwareLayoutSP.__new__(software.SoftwareLayoutSP)
      button_values = []
      layout._branch_btn = SimpleNamespace(action_item=SimpleNamespace(set_value=button_values.append))
      with patch.object(software, "ui_state", SimpleNamespace(params=params)), \
           patch.object(software.HARDWARE, "get_device_type", return_value=device_type), \
           patch.object(software, "get_hardware_profile", return_value=profile, create=True), \
           patch.object(software.gui_app, "font", return_value=rl.Font()), \
           patch.object(software.gui_app, "push_widget") as pushed, \
           patch.object(software.subprocess, "run") as signal:
        software.SoftwareLayoutSP._on_select_branch(layout)
        dialog = layout._branch_dialog
        folders = {folder.folder: [node.ref for node in folder.nodes] for folder in dialog.folders}
        offered = [node.ref for folder in dialog.folders for node in folder.nodes]
        assert set(offered) == set(expected) and len(offered) == len(expected), (name, offered, expected)
        assert not writes and not button_values and signal.call_count == 0
        assert pushed.call_args.args[0] is dialog
        if "dev-sp-egpu-prebuild" in expected:
          assert "dev-sp-egpu-prebuild" in folders["Prebuilt Branches"]
        if "feature-prebuilt" in expected:
          assert "feature-prebuilt" in folders["Prebuilt Branches"]
        if "dev-sp-egpu" in expected:
          assert "dev-sp-egpu" in folders["Non-Prebuilt Branches"]
        dialog.on_exit(DialogResult.CANCEL)
        assert layout._branch_dialog is None and not writes and signal.call_count == 0
        software.SoftwareLayoutSP._on_select_branch(layout)
        layout._branch_dialog.selection_ref = "not-offered"
        layout._branch_dialog.on_exit(DialogResult.CONFIRM)
        assert layout._branch_dialog is None and not writes and signal.call_count == 0
        selected = "dev-sp" if "dev-sp" in offered else None
        if selected:
          software.SoftwareLayoutSP._on_select_branch(layout)
          node = next(node for folder in layout._branch_dialog.folders for node in folder.nodes if node.ref == selected)
          layout._branch_dialog._select_node(node)
          layout._branch_dialog.on_exit(DialogResult.CONFIRM)
          assert writes == [("UpdaterTargetBranch", selected)] and button_values == [selected]
          assert signal.call_args.args[0] == ["pkill", "-SIGUSR1", "-f", "openpilot.system.updated.updated"]
          assert layout._branch_dialog is None
        records.append({"case": name, "device_type": device_type, "profile": str(profile), "installed": current,
                        "folders": folders, "selected": selected, "passed": True})
  sources = [Path(software.__file__), Path("openpilot/sunnypilot/hardware/branches.py"), Path(__file__)]
  result = {"scope": "local actual UI dialog construction and callbacks; updater signalling mocked",
            "device_validation": "pending", "gui_rendering": "not exercised", "cases": records,
            "sha256": {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}}
  args.output.parent.mkdir(parents=True, exist_ok=True)
  args.output.write_text(json.dumps(result, indent=2) + "\n")
  print(args.output)


if __name__ == "__main__":
  main()
