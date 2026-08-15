import copy
import json
from pathlib import Path

from tools.agnos_preflight import EXPECTED_PARTITIONS, load_manifest, validate_manifest


ROOT = Path(__file__).parents[2]
MANIFEST = ROOT / "openpilot/common/hardware/tici/agnos.json"
MR_ONE_DEV_19_6_HASHES = {
  "xbl": "e8acf2a9cc7f0ce84cb803bfea9477f765c0d7b4daf26048e59651b9e6a7bfbb",
  "xbl_config": "758552ecf92b5569677197783bf0ccb73d7f961685308e45d3276ac9dd974f85",
  "abl": "32a2174b5f764e95dfc54cf358ba01752943b1b3b90e626149c3da7d5f1830b6",
  "aop": "78b2287ca219a0811b3004c523fa0f4749e4d1fd92be3aba61699305b7943ad1",
  "devcfg": "f71df3a86958c093ba3969254c4db025187eef9385427f1ade946742939b43cc",
  "boot": "0191529aa97d90d1fa04b472d80230b777606459e1e1e9e2323c9519839827b4",
  "system": "5b6ce7965904a157fd3a134ccfcb854f9ca5c1cc2a26b7cb80a4fa4e1cc4aaa3",
}


def test_runtime_19_6_manifest_is_valid() -> None:
  manifest = load_manifest(MANIFEST)
  assert tuple(partition["name"] for partition in manifest) == EXPECTED_PARTITIONS
  assert validate_manifest(manifest) == []
  assert {partition["name"]: partition["hash_raw"] for partition in manifest} == MR_ONE_DEV_19_6_HASHES


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
