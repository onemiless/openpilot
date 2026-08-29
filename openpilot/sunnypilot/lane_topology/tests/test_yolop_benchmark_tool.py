from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "tools/benchmark_yolop_lane.py"


def test_yolop_benchmark_is_offroad_only_and_never_writes_model_selection_params():
  source = SCRIPT.read_text()
  assert 'get_bool("IsOffroad")' in source
  assert "ModelManager_ActiveBundle" not in source
  assert ".put(" not in source
  assert "YOLOPOnnxLaneModel" in source
  assert "0xF2" in source
  assert "bulk_fail" in source
