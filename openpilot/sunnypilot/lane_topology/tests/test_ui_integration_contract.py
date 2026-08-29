from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


def test_ui_integration_stays_out_of_model_planner_control_and_schema():
  ui_state = (ROOT / "openpilot/selfdrive/ui/sunnypilot/ui_state.py").read_text()
  hud = (ROOT / "openpilot/selfdrive/ui/mici/onroad/hud_renderer.py").read_text()
  assert "LaneTopologyUIBridge" in ui_state
  assert "_draw_lane_topology" in hud
  assert "LANE {lane_number}" in hud
  assert "PubMaster" not in ui_state
  assert "sendcan" not in ui_state
  assert "modelDataV2SP" not in ui_state
