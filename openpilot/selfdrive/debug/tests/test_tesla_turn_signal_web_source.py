from pathlib import Path


WEB_SOURCE = Path(__file__).parents[1] / "tesla_turn_signal_web.py"


def test_lateral_coordinates_are_not_mirrored_on_canvas():
  source = WEB_SOURCE.read_text()
  assert source.count("clientWidth / 2 - y * yScale") == 2
  assert "clientWidth / 2 + y * yScale" not in source


def test_vehicle_distance_sources_are_drawn_with_optional_diagnostics():
  source = WEB_SOURCE.read_text()
  assert "周边目标（原车 CAN）" in source
  assert "前车（SP 视觉模型）" in source
  assert '<details id="can-diagnostics"' in source
  assert "CAN 诊断详情（可选）" in source
  assert "drawCanvasSummary(ctx,can,width)" in source
  assert "drawPedestrianCameraIndicators(ctx,ped,width,height)" in source
  assert "drawParkingObstacle(ctx,can.parking_obstacle||{}" in source
  assert "renderOptionalCanDetails(can,geometry.leads||[])" in source


def test_unverified_pedestrian_coordinate_slots_are_not_drawn_as_metric_positions():
  source = WEB_SOURCE.read_text()
  assert "ped.closest" not in source
  assert "T-CAN 未提供单位和单槽有效位" in source
  assert "行人碰撞告警" in source
