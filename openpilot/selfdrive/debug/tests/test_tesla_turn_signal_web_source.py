from pathlib import Path


WEB_SOURCE = Path(__file__).parents[1] / "tesla_turn_signal_web.py"


def test_lateral_coordinates_are_not_mirrored_on_canvas():
  source = WEB_SOURCE.read_text()
  assert source.count("clientWidth / 2 - y * yScale") == 2
  assert "clientWidth / 2 + y * yScale" not in source


def test_vehicle_distance_sources_are_exposed_in_driving_details():
  source = WEB_SOURCE.read_text()
  assert "周边目标（原车 CAN）" in source
  assert "前车（SP 视觉模型）" in source
  assert "renderCanDetails(can, geometry.leads || [])" in source
