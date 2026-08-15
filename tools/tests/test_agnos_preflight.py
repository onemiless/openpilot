import copy
import json
from pathlib import Path

from tools.agnos_preflight import EXPECTED_PARTITIONS, load_manifest, validate_manifest


ROOT = Path(__file__).parents[2]
MANIFEST = ROOT / "openpilot/common/hardware/tici/agnos-19.6.json"


def test_official_19_6_manifest_is_valid() -> None:
  manifest = load_manifest(MANIFEST)
  assert tuple(partition["name"] for partition in manifest) == EXPECTED_PARTITIONS
  assert validate_manifest(manifest) == []


def test_rejects_non_ab_partition() -> None:
  manifest = load_manifest(MANIFEST)
  modified = copy.deepcopy(manifest)
  modified[0]["has_ab"] = False
  assert "xbl: non-A/B partition is not accepted for this migration" in validate_manifest(modified)


def test_rejects_wrong_partition_order() -> None:
  manifest = load_manifest(MANIFEST)
  modified = copy.deepcopy(manifest)
  modified[0], modified[1] = modified[1], modified[0]
  assert any(error.startswith("partition order/names must be") for error in validate_manifest(modified))


def test_rejects_invalid_hash(tmp_path: Path) -> None:
  manifest = load_manifest(MANIFEST)
  manifest[0]["hash"] = "not-a-hash"
  path = tmp_path / "agnos.json"
  path.write_text(json.dumps(manifest))
  assert "xbl: hash must be a lowercase SHA-256" in validate_manifest(load_manifest(path))
