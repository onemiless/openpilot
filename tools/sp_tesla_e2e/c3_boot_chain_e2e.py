#!/usr/bin/env python3
"""Physical model -> actual launch selection -> guarded updater, without partition IO."""

import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from unittest.mock import patch

from openpilot.common.hardware.comma import agnos
from openpilot.sunnypilot.hardware.agnos import UnsafeBootChainManifest
from openpilot.system.updated import updated

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = {
  "xbl": "e8acf2a9cc7f0ce84cb803bfea9477f765c0d7b4daf26048e59651b9e6a7bfbb",
  "xbl_config": "758552ecf92b5569677197783bf0ccb73d7f961685308e45d3276ac9dd974f85",
  "abl": "32a2174b5f764e95dfc54cf358ba01752943b1b3b90e626149c3da7d5f1830b6",
  "boot": "0191529aa97d90d1fa04b472d80230b777606459e1e1e9e2323c9519839827b4",
}
C3 = "openpilot/common/hardware/comma/agnos-c3.json"


def run(output):
  cases = []
  with tempfile.TemporaryDirectory() as temp:
    directory = Path(temp)
    model = directory / "model"
    for physical, profile, version, manifest in [
      ("tici", "standard", "20.1", C3),
      ("tizi", "standard", "20.1", "openpilot/common/hardware/comma/agnos.json"),
      ("mici", "standard", "20.1", "openpilot/common/hardware/comma/agnos.json"),
      ("tici", "c3xl", "20.1", "openpilot/common/hardware/comma/agnos-c3xl.json"),
    ]:
      model.write_bytes(f"comma {physical}".encode() + b"\0")
      env = os.environ | {"SUNNYPILOT_HARDWARE_PROFILE": profile, "SUNNYPILOT_HARDWARE_MODEL_FILE": str(model), "AGNOS_VERSION": ""}
      selected = subprocess.check_output(
        ["bash", "-c", 'source ./launch_env.sh; printf "%s\n%s\n" "$AGNOS_VERSION" "$AGNOS_MANIFEST_FILE"'], cwd=ROOT, env=env, text=True
      ).splitlines()
      cases.append({"scenario": f"select_{physical}_{profile}", "passed": selected == [version, manifest], "selected": selected})
    model.write_bytes(b"comma tici\0")
    env = {"SUNNYPILOT_HARDWARE_PROFILE": "standard", "SUNNYPILOT_HARDWARE_MODEL_FILE": str(model)}
    with patch.dict(os.environ, env):
      try:
        parts = agnos.load_agnos_manifest(str(ROOT / C3))
        by_name = {p["name"]: p for p in parts}
        assert all(by_name[n]["hash_raw"] == digest and by_name[n]["hash"] == digest for n, digest in EXPECTED.items())
        stock = json.loads((ROOT / "openpilot/common/hardware/comma/agnos.json").read_text())
        assert by_name["system"] == next(p for p in stock if p["name"] == "system")
        cases.append({"scenario": "mr_one_four_images_stock_19_9_system", "passed": True})
        for name in EXPECTED:
          for change in ("hash", "missing", "full_check", "has_ab"):
            altered = copy.deepcopy(parts)
            entry = next(p for p in altered if p["name"] == name)
            if change == "missing":
              altered.remove(entry)
            else:
              entry[change] = "0" * 64 if change == "hash" else False
            damaged = directory / "damaged.json"
            damaged.write_text(json.dumps(altered))
            try:
              agnos.load_agnos_manifest(str(damaged))
            except UnsafeBootChainManifest:
              cases.append({"scenario": f"reject_{name}_{change}", "passed": True})
            else:
              cases.append({"scenario": f"reject_{name}_{change}", "passed": False})
        try:
          agnos.load_agnos_manifest(str(ROOT / "openpilot/common/hardware/comma/agnos.json"))
        except UnsafeBootChainManifest:
          cases.append({"scenario": "reject_stock_boot_chain_on_c3", "passed": True})
        else:
          cases.append({"scenario": "reject_stock_boot_chain_on_c3", "passed": False})
        staged = directory / "candidate"
        (staged / C3).parent.mkdir(parents=True)
        shutil.copyfile(ROOT / C3, staged / C3)
        shutil.copyfile(ROOT / "launch_env.sh", staged / "launch_env.sh")
        flashed = []

        def validate_only(path, slot, log):
          agnos.load_agnos_manifest(path)
          flashed.append({"manifest": str(Path(path).relative_to(staged)), "slot": slot})

        with (
          patch.object(updated, "OVERLAY_MERGED", str(staged)),
          patch.object(updated.HARDWARE, "get_os_version", return_value="19.7"),
          patch.object(updated, "set_consistent_flag"),
          patch.object(agnos, "get_target_slot_number", return_value=0),
          patch.object(agnos, "flash_agnos_update", side_effect=validate_only),
        ):
          updated.handle_agnos_update()
        assert flashed == [{"manifest": C3, "slot": 0}], flashed
        cases.append({"scenario": "actual_updater_uses_guarded_c3_manifest", "passed": True, "boundary": flashed})
      except (FileNotFoundError, AssertionError) as error:
        cases.append({"scenario": "c3_manifest_closure", "passed": False, "error": str(error)})
  result = {
    "passed": all(c["passed"] for c in cases),
    "scope": "actual shell/updater/manifest validation; no partition writes",
    "source_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
    "cases": cases,
  }
  output.parent.mkdir(parents=True, exist_ok=True)
  output.write_text(json.dumps(result, indent=2) + "\n")
  print(json.dumps({"passed": result["passed"], "cases": len(cases), "output": str(output)}))
  return result["passed"]


if __name__ == "__main__":
  parser = argparse.ArgumentParser()
  parser.add_argument("--output", type=Path, required=True)
  raise SystemExit(0 if run(parser.parse_args().output) else 1)
