import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


def test_v1_benchmark_tool_contract():
  source = (ROOT / "tools/benchmark_ufldv1_lane.py").read_text()
  ast.parse(source)
  assert 'get_bool("IsOffroad")' in source
  assert "USB3.control_write" in source
  assert "USB3.bulk_read" in source
  assert 'with path.open("x")' in source
