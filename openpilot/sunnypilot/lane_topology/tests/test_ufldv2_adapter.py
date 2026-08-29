from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


def test_ufldv2_adapter_delays_tinygrad_import_until_model_construction():
  source = (ROOT / "openpilot/sunnypilot/lane_topology/ufldv2_adapter.py").read_text()
  before_model = source.split("class UFLDv2OnnxLaneModel", 1)[0]
  assert "from tinygrad" not in before_model
  assert "from tinygrad" in source
  assert "USB3" not in source
  assert "AMDDevice" not in source


def test_official_export_hash_is_bound_in_source():
  source = (ROOT / "openpilot/sunnypilot/lane_topology/ufldv2_adapter.py").read_text()
  assert "ea26570cc22ded75364e6a151236b8a496e9f700775501b4ed0f10c2c3204dc0" in source
