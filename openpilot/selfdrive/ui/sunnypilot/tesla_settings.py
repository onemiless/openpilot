"""Tesla setting metadata and guarded tuning access shared by native layouts."""
from openpilot.system.ui.lib.multilang import tr_noop
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_backends.tuning import (
  apply_backend_profile, backend_values, save_backend_values,
)

LABELS = {
 'TeslaCoopSteering': 'Cooperative Steering', 'TeslaTouchLongitudinalSwitch': '4-Finger Longitudinal Switch',
 'TeslaApHybrid': 'AP Hybrid Control', 'TeslaDynamicApLongitudinal': 'Dynamic AP Control',
 'DynamicAutoStock': 'Dynamic Stock ACC', 'DynamicAutoStockBlinkerToSP': 'Turn Signal to SP Longitudinal',
 'DynamicAutoStockCurveToSP': 'Curve to SP Longitudinal',
 'TeslaTrafficSignalControlEnabled': 'Traffic Light Control',
 'TeslaBlindspotAmbientEnabled': 'Blindspot Ambient Lights', 'AccelPersonalityEnabled': 'TN Accel Personality',
 'TeslaARS408Radar': 'Radar Source', 'TeslaMadsScreenButton': 'MADS Touch Gesture',
 'AccelPersonality': 'TN Accel Profile', 'DynamicAutoStockSpeedKph': 'Stock ACC Entry Speed',
 'DynamicAutoStockSpeedLowKph': 'Stock ACC Exit Speed', 'TeslaTrafficStopReference': 'Traffic Light Stop Distance',
 'TeslaTrafficControlMaxSpeed': 'Traffic Control Max Speed',
 'TeslaBlindspotAmbientDayBrightness': 'Blindspot Day Brightness', 'TeslaBlindspotAmbientBrightness': 'Blindspot Night Brightness',
 't_follow_relaxed': 'Relaxed Follow Time', 't_follow_standard': 'Standard Follow Time', 't_follow_aggressive': 'Aggressive Follow Time',
 'x_ego_obstacle_cost': 'Obstacle Cost', 'j_ego_cost': 'Jerk Cost', 'a_change_cost': 'Accel Change Cost',
 'danger_zone_cost': 'Danger Zone Cost', 'lead_danger_factor': 'Lead Danger Factor',
 'comfort_brake': 'Comfort Brake', 'stop_distance': 'Stop Distance', 'jerk_factor_relaxed': 'Relaxed Jerk Factor',
}

# C3 titles support localization; mici labels stay in English for font support.
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


INVALID_CONFIG = 'Cannot read tuning configuration. Original data preserved. Restore a valid configuration before saving.'


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
    return None, 'Not saved: invalid tuning configuration or selected preset.'


def save_tuning(params, backend, values):
  _, error = load_tuning(params, backend)
  if error:
    return error
  try:
    save_backend_values(params, backend, values, 2)
    return ''
  except ValueError:
    return 'Not saved: invalid values or following times out of order.'


# Kept in the UI source so font glyph collection covers the provider's notice.
OFFICIAL_TUNING_NOTICE = ('Official keeps the upstream six-parameter solver. Comfort Brake and Stop Distance use obstacle-shift approximations, ' +
                        'not equivalent eight-parameter MPC tuning. Defaults preserve upstream behavior.')


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
