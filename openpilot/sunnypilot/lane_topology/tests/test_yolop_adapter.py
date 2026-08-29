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
  assert "03690d106c5e59f8c6c55aa9a24b4bca795db1c7e1335887e26c50f43ee2feaf" in source
  assert "b7b09f3e918627b124943dcb7fa819b4c6968c7528f8eef9a474a082d4ef65ba" in source
