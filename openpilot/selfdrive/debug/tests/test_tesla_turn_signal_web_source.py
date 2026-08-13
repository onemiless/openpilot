from pathlib import Path


WEB_SOURCE = Path(__file__).parents[1] / "tesla_turn_signal_web.py"


def test_model_and_oem_lateral_coordinates_use_their_own_screen_conventions():
  source = WEB_SOURCE.read_text()
  assert "function drawModelLine" in source
  assert "clientWidth / 2 + y * yScale" in source
  assert "function modelCanvasPoint" in source
  assert "clientWidth / 2 - y * yScale" in source
  assert "drawModelLine(ctx, geometry.path || []" in source
  assert "drawLine(ctx,oemLanes.left||[]" in source


def test_vehicle_distance_sources_are_drawn_with_optional_diagnostics():
  source = WEB_SOURCE.read_text()
  assert "周边目标 · DAS_object 0x30A（CH）" in source
  assert "前车（SP 视觉模型）" not in source
  assert "原车目标能力边界" not in source
  assert "盲区 / 侧碰" not in source
  assert "PMM / 碰撞摘要" not in source
  assert '<details id="can-diagnostics"' in source
  assert "CAN 诊断详情（可选）" in source
  assert "drawCanvasSummary(ctx,can,width)" in source
  assert "drawPedestrianCameraIndicators(ctx,ped,width,height)" in source
  assert "drawParkingObstacle(ctx,can.parking_obstacle||{}" in source
  assert "renderOptionalCanDetails(can)" in source
  assert "SP '+Math.round(lead.x)+'m'" in source
  assert "交通控制 · 0x25D" in source
  assert "灯态：" in source
  assert "来源：" in source
  assert "距离：" in source
  assert "state=" in source
  assert "功能状态：" in source
  assert "traffic.light_observation_available" in source


def test_unverified_pedestrian_coordinate_slots_require_explicit_experiment_mode():
  source = WEB_SOURCE.read_text()
  assert "ped.closest" not in source
  assert "原始坐标槽：" in source
  assert "行人碰撞告警" not in source
  assert '<select id="pedestrian-coordinate-mode"' in source
  assert '<option value="off">关闭（默认）</option>' in source
  assert "dx_forward_dy_left" in source
  assert "dx_forward_dy_right" in source
  assert "dy_forward_dx_left" in source
  assert "dy_forward_dx_right" in source
  assert "drawExperimentalPedestrianSlots(ctx,ped,xScale,yScale,width,height)" in source
  assert "localStorage.getItem('pedestrianCoordinateMode') || 'off'" in source
  assert "实验解析：" in source
  assert "原始前后位同时置位" in source
