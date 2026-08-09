from openpilot.selfdrive.carrot.carrot_man import CarrotMan


def test_get_radar_data_preserves_original_error():
  carrot = CarrotMan.__new__(CarrotMan)
  carrot.sm = None

  result = carrot.get_radar_data()

  assert result["points"] == []
  assert "NoneType" in result["error"]
