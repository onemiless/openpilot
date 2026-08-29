from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


def test_v1_adapter_delays_tinygrad_import_until_model_construction():
  source = (ROOT / "openpilot/sunnypilot/lane_topology/ufldv1_adapter.py").read_text()
  before_model = source.split("class UFLDv1OnnxLaneModel", 1)[0]
  assert "from tinygrad" not in before_model
  assert "from tinygrad" in source
  assert "USB3" not in source


def test_v1_official_export_hash_is_bound():
  source = (ROOT / "openpilot/sunnypilot/lane_topology/ufldv1_adapter.py").read_text()
  assert "46a1864bcc8c13497fe0c18d4584fed993482d5170d3152ef5e138ff1e471b2d" in source
