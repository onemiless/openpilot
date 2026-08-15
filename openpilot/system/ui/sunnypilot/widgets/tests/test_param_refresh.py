from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.sunnypilot.widgets.list_view import ListItemSP, MultipleButtonActionSP, ToggleActionSP
from openpilot.system.ui.sunnypilot.widgets.option_control import OptionControlSP
from openpilot.system.ui.sunnypilot.widgets.toggle import ToggleSP


def test_toggle_refreshes_param_when_page_is_reopened():
  toggle = ToggleSP(param="DynamicAutoStockCurveToSP")
  assert not toggle.get_state()

  toggle.params.put_bool("DynamicAutoStockCurveToSP", True, block=True)
  toggle.show_event()

  assert toggle.get_state()


def test_list_item_propagates_page_reopen_to_param_action(monkeypatch):
  monkeypatch.setattr(gui_app, "font", lambda *_args, **_kwargs: object())
  action = ToggleActionSP(param="DynamicAutoStockCurveToSP")
  item = ListItemSP(action_item=action)
  action.toggle.params.put_bool("DynamicAutoStockCurveToSP", True, block=True)

  item.show_event()

  assert action.get_state()


def test_multiple_button_refreshes_param_when_page_is_reopened(monkeypatch):
  monkeypatch.setattr(gui_app, "font", lambda *_args, **_kwargs: object())
  action = MultipleButtonActionSP(["Off", "3-Finger", "5-Finger"], 100, param="TeslaMadsScreenButton")
  assert action.get_selected_button() == 0

  action.params.put("TeslaMadsScreenButton", 2, block=True)
  action.show_event()

  assert action.get_selected_button() == 2


def test_option_refreshes_param_when_page_is_reopened(monkeypatch):
  monkeypatch.setattr(gui_app, "font", lambda *_args, **_kwargs: object())
  action = OptionControlSP("DynamicAutoStockSpeedKph", 40, 120, value_change_step=5)
  assert action.get_value() == 80

  action.params.put("DynamicAutoStockSpeedKph", 95, block=True)
  action.show_event()

  assert action.get_value() == 95
