"""Tesla setting metadata and guarded tuning access shared by native layouts."""
from openpilot.system.ui.lib.multilang import tr_noop
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_backends.tuning import (
  apply_backend_profile, backend_values, save_backend_values,
)

LABELS = {
 'TeslaCoopSteering': '协同转向', 'TeslaTouchLongitudinalSwitch': '四指切换纵向',
 'TeslaApHybrid': 'AP 混合控制', 'TeslaDynamicApLongitudinal': '动态 AP 控制',
 'DynamicAutoStock': '动态原车 ACC', 'DynamicAutoStockBlinkerToSP': '转向灯切回 SP 纵向',
 'DynamicAutoStockCurveToSP': '弯道切回 SP 纵向',
 'TeslaTrafficSignalControlEnabled': '交通灯控制',
 'TeslaBlindspotAmbientEnabled': '盲区氛围灯联动', 'AccelPersonalityEnabled': 'TN 加速风格',
 'TeslaARS408Radar': '雷达来源', 'TeslaMadsScreenButton': 'MADS 触屏手势',
 'AccelPersonality': 'TN 加速模式', 'DynamicAutoStockSpeedKph': '原车 ACC 切入速度',
 'DynamicAutoStockSpeedLowKph': '原车 ACC 退出速度', 'TeslaTrafficStopReference': '交通灯停车距离',
 'TeslaTrafficControlMaxSpeed': '交通灯控制最高速度',
 'TeslaBlindspotAmbientDayBrightness': '盲区灯白天亮度', 'TeslaBlindspotAmbientBrightness': '盲区灯夜间亮度',
 't_follow_relaxed': '舒适跟车时间', 't_follow_standard': '标准跟车时间', 't_follow_aggressive': '激进跟车时间',
 'x_ego_obstacle_cost': '障碍物权重', 'j_ego_cost': '加加速度权重', 'a_change_cost': '加速度变化权重',
 'danger_zone_cost': '危险区域权重', 'lead_danger_factor': '前车危险系数',
 'comfort_brake': '舒适制动', 'stop_distance': '停车距离', 'jerk_factor_relaxed': '舒适模式加加速度系数',
}

# Existing C3 titles and mici labels stay localized while their keys live together.
TITLES = {
  'TeslaCoopSteering': tr_noop('Cooperative Steering (Beta)'), 'TeslaMadsScreenButton': tr_noop('MADS Screen Activation'),
  'TeslaTouchLongitudinalSwitch': tr_noop('4-Finger Longitudinal Switch'), 'TeslaApHybrid': tr_noop('AP Hybrid Control (Experimental)'),
  'TeslaDynamicApLongitudinal': tr_noop('Dynamic AP Control (Experimental)'), 'DynamicAutoStock': tr_noop('Dynamic Auto Stock ACC'),
  'DynamicAutoStockBlinkerToSP': tr_noop('Turn Signal → SP Longitudinal'), 'DynamicAutoStockCurveToSP': tr_noop('Curve → SP Longitudinal'),
  'DynamicAutoStockSpeedKph': tr_noop('Speed Threshold High'), 'DynamicAutoStockSpeedLowKph': tr_noop('Speed Threshold Low'),
  'TeslaARS408Radar': tr_noop('Tesla Radar Backend'), 'TeslaTrafficSignalControlEnabled': tr_noop('Traffic Light Control (Experimental)'),
  'TeslaTrafficStopReference': tr_noop('Traffic Light Stop Reference'), 'TeslaTrafficControlMaxSpeed': tr_noop('Traffic Light Control Maximum Speed'),
  'TeslaBlindspotAmbientEnabled': tr_noop('盲区联动氛围灯'), 'TeslaBlindspotAmbientDayBrightness': tr_noop('盲区氛围灯：白天亮度'),
  'TeslaBlindspotAmbientBrightness': tr_noop('盲区氛围灯：夜间亮度'), 'AccelPersonality': tr_noop('TN Accel Profile'),
  'AccelPersonalityEnabled': tr_noop('TN Accel Personality'),
}

BOOL_KEYS = (
  'TeslaCoopSteering', 'TeslaTouchLongitudinalSwitch', 'TeslaApHybrid',
  'TeslaDynamicApLongitudinal', 'DynamicAutoStock', 'DynamicAutoStockBlinkerToSP',
  'DynamicAutoStockCurveToSP', 'TeslaTrafficSignalControlEnabled',
  'TeslaBlindspotAmbientEnabled', 'AccelPersonalityEnabled',
)
RANGES = {
  'DynamicAutoStockSpeedKph': (40, 120, 5, 'km/h', 1),
  'DynamicAutoStockSpeedLowKph': (20, 115, 5, 'km/h', 1),
  'TeslaTrafficStopReference': (20, 120, 5, 'm', 10),
  'TeslaTrafficControlMaxSpeed': (20, 120, 5, 'km/h', 1),
  'TeslaBlindspotAmbientDayBrightness': (0, 100, 1, '%', 1),
  'TeslaBlindspotAmbientBrightness': (0, 100, 1, '%', 1),
}
CHOICES = {
  'TeslaARS408Radar': [('OEM', 0), ('ARS408', 1), ('Off', 2)],
  'TeslaMadsScreenButton': [('Off', 0), ('3-Finger', 1), ('5-Finger', 2)],
  'AccelPersonality': [('Eco', 0), ('Normal', 1), ('Sport', 2)],
}


def setting_label(key, value):
  if key in RANGES:
    _, _, _, unit, divisor = RANGES[key]
    number = f'{value / divisor:.1f}' if divisor != 1 else str(value)
    return number + ('%' if unit == '%' else ' ' + unit)
  return next((label for label, choice in CHOICES[key] if choice == value), str(value))


for key, (minimum, maximum, step, _, _) in RANGES.items():
  CHOICES[key] = [(setting_label(key, value), value) for value in range(minimum, maximum + 1, step)]


def option_kwargs(key):
  minimum, maximum, step, _, _ = RANGES[key]
  return {'min_value': minimum, 'max_value': maximum, 'value_change_step': step,
          'label_callback': lambda value: setting_label(key, value)}


INVALID_CONFIG = '调参配置无法读取，已保留原始数据。请先恢复有效配置；当前禁止保存。'


def load_tuning(params, backend):
  try:
    return backend_values(params, backend), ''
  except ValueError:
    return None, INVALID_CONFIG


def apply_tuning_profile(params, backend, profile):
  _, error = load_tuning(params, backend)
  if error:
    return None, error
  try:
    return apply_backend_profile(params, backend, profile), ''
  except ValueError:
    return None, '参数未保存：调参配置或所选预设无效。'


def save_tuning(params, backend, values):
  _, error = load_tuning(params, backend)
  if error:
    return error
  try:
    save_backend_values(params, backend, values, 2)
    return ''
  except ValueError:
    return '参数未保存：数值无效或跟车时间顺序不正确。'


# Kept in the UI source so font glyph collection covers the provider's notice.
OFFICIAL_TUNING_NOTICE = 'Official 保持官方六参数求解器；舒适制动与停车距离通过障碍物平移近似实现，非八参数 MPC 的等价调参。默认值不改变官方行为。'


def tuning_notice(backend):
  return backend.tuning_notice or (OFFICIAL_TUNING_NOTICE if backend.slug == 'official' else '')


TUNING_ITEMS = (
  ("stop_distance", "MpcStopDistance", tr_noop("Stop Distance"), "m"),
  ("comfort_brake", "MpcComfortBrake", tr_noop("Comfort Brake"), "m/s²"),
  ("lead_danger_factor", "MpcLeadDangerFactor", tr_noop("Lead Danger Factor"), ""),
  ("t_follow_relaxed", "MpcTFollowRelaxed", tr_noop("T Follow Relaxed"), "s"),
  ("t_follow_standard", "MpcTFollowStandard", tr_noop("T Follow Standard"), "s"),
  ("t_follow_aggressive", "MpcTFollowAggressive", tr_noop("T Follow Aggressive"), "s"),
  ("x_ego_obstacle_cost", "MpcXObstacleCost", tr_noop("Obstacle Cost"), ""),
  ("j_ego_cost", "MpcJerkCost", tr_noop("Jerk Cost"), ""),
  ("jerk_factor_relaxed", "MpcJerkFactorStandard", tr_noop("Relaxed Jerk Factor"), ""),
  ("a_change_cost", "MpcAccelChangeCost", tr_noop("Accel Change Cost"), ""),
  ("danger_zone_cost", "MpcDangerZoneCost", tr_noop("Danger Zone Cost"), ""),
)

TUNING_UNITS = {field: unit for field, _, _, unit in TUNING_ITEMS}
