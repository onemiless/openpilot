import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


def test_route_replay_tool_is_shadow_only_and_requires_synchronized_inputs():
  source = (ROOT / "tools/replay_primary_lane_topology.py").read_text()
  ast.parse(source)
  assert "modelV2" in source
  assert "qNarrowRoadEncodeIdx" in source
  assert "qcamera.ts" in source
  assert "--video-name" in source
  assert "--blur-sigma" in source
  assert "--disable-adaptive-marking" in source
  assert "PubMaster" not in source
  assert "Params" not in source
  assert "sendcan" not in source
