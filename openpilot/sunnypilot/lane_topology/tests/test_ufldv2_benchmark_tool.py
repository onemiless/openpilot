import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


def test_ufldv2_benchmark_tool_is_syntactically_valid_and_offroad_gated():
  source = (ROOT / "tools/benchmark_ufldv2_lane.py").read_text()
  ast.parse(source)
  assert 'get_bool("IsOffroad")' in source
  assert "USB3.control_write" in source
  assert "USB3.bulk_read" in source
  assert 'request == 0xF2' in source
  assert 'with path.open("x")' in source
