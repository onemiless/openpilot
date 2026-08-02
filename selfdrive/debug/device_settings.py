"""Whitelisted settings exposed by the local device settings web UI.

The web server must never provide a generic Params write endpoint: many Params
contain credentials, calibration, or safety state.  This module derives the
normal user-facing settings from sunnypilot's UI schema and adds the local
Tesla/MPC controls that are intentionally maintained outside that schema.
"""
import json
import math
from pathlib import Path
from typing import Any

from openpilot.common.params import Params


SETTINGS_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "sunnypilot" / "sunnylink" / "settings_ui.json"

# These controls are user settings in this branch but have no SunnyLink schema
# entry.  Only MPC values are allowed onroad: the MPC reloads them at runtime.
EXTRA_SETTINGS: tuple[dict[str, Any], ...] = (
  {"key": "TeslaApHybrid", "widget": "toggle", "title": "Tesla AP 混合控制", "group": "Tesla", "offroad_only": True},
  {"key": "TeslaDynamicApLongitudinal", "widget": "toggle", "title": "Tesla 动态 AP 纵向", "group": "Tesla", "offroad_only": True},
  {"key": "TeslaAutoSpeedLimit", "widget": "toggle", "title": "Tesla 自动限速", "group": "Tesla", "offroad_only": False},
  {"key": "DynamicAutoStockBlinkerToSP", "widget": "toggle", "title": "动态原车：转向灯切换 SP", "group": "Tesla", "offroad_only": True},
  {"key": "DynamicAutoStockCurveToSP", "widget": "toggle", "title": "动态原车：弯道切换 SP", "group": "Tesla", "offroad_only": True},
  {"key": "DynamicAutoStockSpeedKph", "widget": "option", "title": "动态原车切换速度", "group": "Tesla", "min": 0, "max": 200, "step": 1, "unit": "km/h", "offroad_only": True},
  {"key": "DynamicAutoStockSpeedLowKph", "widget": "option", "title": "动态原车回切速度", "group": "Tesla", "min": 0, "max": 200, "step": 1, "unit": "km/h", "offroad_only": True},
  {"key": "TeslaMadsScreenButton", "widget": "multiple_button", "title": "Tesla MADS 屏幕按钮", "group": "Tesla", "options": [{"value": 0, "label": "关闭"}, {"value": 1, "label": "开启"}], "offroad_only": True},
  {"key": "TeslaOfflineWakeCaptureEnabled", "widget": "toggle", "title": "离线唤醒诊断记录", "group": "Tesla", "offroad_only": True},
  {"key": "MpcTuningPreset", "widget": "multiple_button", "title": "纵向 MPC 预设", "group": "纵向 MPC", "options": [{"value": 0, "label": "Moumou"}, {"value": 1, "label": "当前"}, {"value": 2, "label": "自定义"}], "offroad_only": False},
)

MPC_FIELDS = (
  ("MpcXObstacleCost", "障碍物代价", 0, 1000, 1),
  ("MpcJerkCost", "加加速度代价", 0, 2000, 1),
  ("MpcAccelChangeCost", "加速度变化代价", 0, 50000, 100),
  ("MpcDangerZoneCost", "危险区代价", 0, 50000, 100),
  ("MpcLeadDangerFactor", "前车危险系数", 0, 300, 1),
  ("MpcComfortBrake", "舒适制动", 0, 600, 1),
  ("MpcStopDistance", "停车距离", 0, 2000, 10),
  ("MpcJerkFactorStandard", "标准跟车加加速度系数", 0, 300, 1),
  ("MpcTFollowRelaxed", "舒适跟车时距", 50, 400, 1),
  ("MpcTFollowStandard", "标准跟车时距", 50, 400, 1),
  ("MpcTFollowAggressive", "激进跟车时距", 50, 400, 1),
)


def _has_offroad_only(value: Any) -> bool:
  if isinstance(value, dict):
    if value.get("type") == "offroad_only":
      return True
    return any(_has_offroad_only(child) for child in value.values())
  if isinstance(value, list):
    return any(_has_offroad_only(child) for child in value)
  return False


def _schema_settings() -> list[dict[str, Any]]:
  schema = json.loads(SETTINGS_SCHEMA_PATH.read_text())
  settings: list[dict[str, Any]] = []

  def walk(value: Any, panel: str = "通用", section: str = "") -> None:
    if isinstance(value, dict):
      current_panel = value.get("label", panel)
      current_section = value.get("title", section)
      if "key" in value and value.get("widget") in {"toggle", "option", "multiple_button"}:
        setting = {k: value[k] for k in ("key", "widget", "title", "description", "details", "options", "min", "max", "step", "unit", "value_map", "needs_onroad_cycle") if k in value}
        setting["group"] = current_panel if not section else f"{panel} / {section}"
        setting["offroad_only"] = _has_offroad_only(value.get("enablement", []))
        settings.append(setting)
      for child_key, child in value.items():
        if child_key not in {"options", "enablement", "visibility", "trigger_condition"}:
          walk(child, current_panel, current_section)
    elif isinstance(value, list):
      for child in value:
        walk(child, panel, section)

  walk(schema)
  return settings


def get_settings() -> dict[str, dict[str, Any]]:
  settings = _schema_settings()
  settings.extend(EXTRA_SETTINGS)
  settings.extend({
    "key": key, "widget": "option", "title": title, "group": "纵向 MPC", "min": minimum, "max": maximum,
    "step": step, "unit": "原始整数值", "offroad_only": False,
  } for key, title, minimum, maximum, step in MPC_FIELDS)
  # Duplicate keys in a nested schema are harmless; retain the first canonical definition.
  return {setting["key"]: setting for setting in settings}


def _read_value(params: Params, setting: dict[str, Any]) -> bool | int | float | str:
  if setting["widget"] == "toggle":
    return params.get_bool(setting["key"])
  value = params.get(setting["key"], return_default=True)
  options = setting.get("options")
  if options:
    allowed_values = {option["value"] for option in options}
    if "" in allowed_values and not value:
      return ""
    if any(isinstance(option, float) for option in allowed_values):
      return float(value) if value is not None else 0.0
  return int(value) if value is not None else 0


def settings_snapshot(params: Params | None = None) -> dict[str, Any]:
  params = params or Params()
  settings = get_settings()
  return {
    "onroad": params.get_bool("IsOnroad"),
    "settings": [{**setting, "value": _read_value(params, setting)} for setting in settings.values()],
  }


def validate_and_write(key: str, value: Any, params: Params | None = None) -> dict[str, Any]:
  params = params or Params()
  setting = get_settings().get(key)
  if setting is None:
    raise KeyError(key)
  if setting["offroad_only"] and params.get_bool("IsOnroad"):
    raise PermissionError("该设置只能在停车后的设置模式修改")

  if setting["widget"] == "toggle":
    if not isinstance(value, bool):
      raise ValueError("开关值必须是 true 或 false")
    params.put_bool(key, value, block=True)
  else:
    options = setting.get("options")
    if options is not None:
      allowed_values = {option["value"] for option in options}
      if value not in allowed_values:
        raise ValueError("不支持的选项值")
    else:
      if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("数值设置必须是有限数字")
      if int(value) != value:
        raise ValueError("该设置只接受整数")
      value = int(value)
    minimum, maximum = setting.get("min"), setting.get("max")
    if minimum is not None and not minimum <= value <= maximum:
      raise ValueError(f"数值必须在 {minimum} 到 {maximum} 之间")
    step = setting.get("step")
    if step and minimum is not None and (value - minimum) % step:
      raise ValueError(f"数值必须按 {step} 递增")
    params.put(key, str(value), block=True)
  return {**setting, "value": _read_value(params, setting)}
