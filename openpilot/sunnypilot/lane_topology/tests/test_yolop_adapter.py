from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


def test_yolop_adapter_delays_all_tinygrad_imports_until_model_construction():
  source = (ROOT / "openpilot/sunnypilot/lane_topology/yolop_adapter.py").read_text()
  before_model = source.split("class YOLOPOnnxLaneModel", 1)[0]
  assert "from tinygrad" not in before_model
  assert "from tinygrad" in source
  assert "USB3" not in source
  assert "AMDDevice" not in source


def test_official_model_hash_is_bound_in_source():
  source = (ROOT / "openpilot/sunnypilot/lane_topology/yolop_adapter.py").read_text()
  assert "86d6e8b6dfdef195c061e9bcad82d9487bb5ee1ac4a1cf9a3dc4736657a07369" in source
