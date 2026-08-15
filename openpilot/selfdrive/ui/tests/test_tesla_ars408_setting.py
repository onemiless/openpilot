import ast
from pathlib import Path


TESLA_SETTINGS = Path("openpilot/selfdrive/ui/sunnypilot/layouts/settings/vehicle/brands/tesla.py")


def test_tesla_vehicle_settings_exposes_offroad_ars408_toggle() -> None:
  tree = ast.parse(TESLA_SETTINGS.read_text())
  calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and
           isinstance(node.func, ast.Name) and node.func.id == "toggle_item_sp"]
  ars408_calls = [call for call in calls if any(
    keyword.arg == "param" and isinstance(keyword.value, ast.Constant) and keyword.value.value == "TeslaARS408Radar"
    for keyword in call.keywords
  )]
  assert len(ars408_calls) == 1
  enabled = next(keyword.value for keyword in ars408_calls[0].keywords if keyword.arg == "enabled")
  assert isinstance(enabled, ast.Attribute) and enabled.attr == "is_offroad"


def test_tesla_vehicle_settings_places_ars408_toggle_in_main_item_list() -> None:
  source = TESLA_SETTINGS.read_text()
  assert "self.items = [self.ars408_radar_toggle," in source
