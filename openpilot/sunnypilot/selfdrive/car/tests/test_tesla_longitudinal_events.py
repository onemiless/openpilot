from types import SimpleNamespace

from openpilot.cereal import custom
from openpilot.selfdrive.selfdrived.events import Events
from openpilot.sunnypilot.selfdrive.car.car_specific import CarSpecificEventsSP
from openpilot.sunnypilot.selfdrive.selfdrived.events import ET


def test_tesla_stock_longitudinal_edge_events_round_trip():
  event_name = custom.OnroadEventSP.EventName
  events = Events()
  helper = CarSpecificEventsSP(SimpleNamespace(brand="tesla"), SimpleNamespace())

  activated = helper.update(SimpleNamespace(), events, 32)
  assert activated.names == [event_name.stockLongitudinalActive]
  assert activated.to_msg()[0].name == event_name.stockLongitudinalActive
  assert activated.create_alerts([ET.WARNING])[0].alert_text_1 == "原车ACC：激活"

  assert helper.update(SimpleNamespace(), events, 32).names == []

  deactivated = helper.update(SimpleNamespace(), events, 0)
  assert deactivated.names == [event_name.stockLongitudinalInactive]
  assert deactivated.to_msg()[0].name == event_name.stockLongitudinalInactive
  assert deactivated.create_alerts([ET.WARNING])[0].alert_text_1 == "OP 纵向：激活"


def test_custom_event_wire_numbers_remain_compatible():
  event_name = custom.OnroadEventSP.EventName
  assert int(event_name.stockLongitudinalActive) == 24
  assert int(event_name.stockLongitudinalInactive) == 25
  assert int(event_name.laneChangeRoadEdge) == 26
