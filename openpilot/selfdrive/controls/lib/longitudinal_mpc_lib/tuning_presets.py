import json
from typing import Any


MPC_PRESET_MOUMOU = 0
MPC_PRESET_CURRENT = 1
MPC_PRESET_CUSTOM = 2

MPC_PRESET_LABELS = {
  MPC_PRESET_MOUMOU: "dev260628XL",
  MPC_PRESET_CURRENT: "Current",
  MPC_PRESET_CUSTOM: "Custom",
}

MPC_PRESET_VALUE_PARAMS = {
  MPC_PRESET_MOUMOU: "MpcTuningMoumouValues",
  MPC_PRESET_CURRENT: "MpcTuningCurrentValues",
}

MPC_PRESETS = {
  MPC_PRESET_MOUMOU: {
    "MpcXObstacleCost": 300,
    "MpcJerkCost": 500,
    "MpcAccelChangeCost": 20000,
    "MpcDangerZoneCost": 10000,
    "MpcLeadDangerFactor": 75,
    "MpcComfortBrake": 250,
    "MpcStopDistance": 600,
    "MpcJerkFactorStandard": 100,
    "MpcTFollowRelaxed": 175,
    "MpcTFollowStandard": 145,
    "MpcTFollowAggressive": 125,
  },
  MPC_PRESET_CURRENT: {
    "MpcXObstacleCost": 500,
    "MpcJerkCost": 300,
    "MpcAccelChangeCost": 10000,
    "MpcDangerZoneCost": 8000,
    "MpcLeadDangerFactor": 35,
    "MpcComfortBrake": 270,
    "MpcStopDistance": 450,
    "MpcJerkFactorStandard": 80,
    "MpcTFollowRelaxed": 165,
    "MpcTFollowStandard": 135,
    "MpcTFollowAggressive": 100,
  },
}

MPC_TUNING_KEYS = tuple(MPC_PRESETS[MPC_PRESET_MOUMOU])


def _live_values(params: Any) -> dict[str, int]:
  return {key: int(params.get(key, return_default=True)) for key in MPC_TUNING_KEYS}


def get_preset_values(params: Any, preset: int) -> dict[str, int]:
  if preset == MPC_PRESET_CUSTOM:
    return _live_values(params)
  if preset not in MPC_PRESETS:
    raise ValueError(f"unknown MPC preset: {preset}")

  values = dict(MPC_PRESETS[preset])
  saved = params.get(MPC_PRESET_VALUE_PARAMS[preset])
  if saved:
    if isinstance(saved, dict):
      saved_values = saved
    else:
      try:
        saved_values = json.loads(saved)
      except (TypeError, json.JSONDecodeError):
        saved_values = {}
    if isinstance(saved_values, dict):
      for key, value in saved_values.items():
        if key in values:
          values[key] = int(value)
  return values


def write_live_values(params: Any, values: dict[str, int]) -> None:
  for key in MPC_TUNING_KEYS:
    params.put(key, int(values[key]))


def save_preset_values(params: Any, preset: int, values: dict[str, int]) -> None:
  storage_key = MPC_PRESET_VALUE_PARAMS.get(preset)
  if storage_key is not None:
    params.put(storage_key, {key: int(values[key]) for key in MPC_TUNING_KEYS})


def apply_preset(params: Any, preset: int) -> dict[str, int]:
  values = get_preset_values(params, preset)
  write_live_values(params, values)
  params.put("MpcTuningPreset", preset)
  return values
