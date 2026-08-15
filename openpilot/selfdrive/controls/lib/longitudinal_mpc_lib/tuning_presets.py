import json
from typing import Any


MPC_PROFILE_DEFAULT = 0
MPC_PROFILE_CRAZYMAX = 1
MPC_PROFILE_CURRENT = 2
MPC_PROFILE_CUSTOM = 3

MPC_PROFILE_LABELS = {
  MPC_PROFILE_DEFAULT: "Default",
  MPC_PROFILE_CRAZYMAX: "CrazyMax",
  MPC_PROFILE_CURRENT: "Current",
  MPC_PROFILE_CUSTOM: "Custom",
}

MPC_PROFILE_VALUE_PARAMS = {
  MPC_PROFILE_DEFAULT: "MpcTuningOfficialValues",
  # Retain the historical storage key so existing CrazyMax tuning is preserved.
  MPC_PROFILE_CRAZYMAX: "MpcTuningMoumouValues",
  MPC_PROFILE_CURRENT: "MpcTuningCurrentValues",
}

MPC_OFFICIAL_VALUES = {
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
}

# Verified against moumou/dev260628XL-tici. The numerical baseline currently
# matches upstream, but it is intentionally independent: CrazyMax selects a
# different planner/MPC implementation and must never fall back by aliasing the
# Default dictionary.
MPC_CRAZYMAX_VALUES = dict(MPC_OFFICIAL_VALUES)

MPC_PROFILES = {
  MPC_PROFILE_DEFAULT: MPC_OFFICIAL_VALUES,
  MPC_PROFILE_CRAZYMAX: MPC_CRAZYMAX_VALUES,
  MPC_PROFILE_CURRENT: {
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

MPC_TUNING_KEYS = tuple(MPC_OFFICIAL_VALUES)
# The tunable SP adapter uses its own eight-parameter solver contract.
OFFICIAL_MPC_TUNING_KEYS = MPC_TUNING_KEYS


def get_mpc_tuning_profile(params: Any) -> int:
  try:
    profile = int(params.get("MpcTuningProfile", return_default=True))
  except (TypeError, ValueError):
    profile = MPC_PROFILE_DEFAULT
  return profile if profile in MPC_PROFILE_LABELS else MPC_PROFILE_DEFAULT


def _live_values(params: Any) -> dict[str, int]:
  return {key: int(params.get(key, return_default=True)) for key in MPC_TUNING_KEYS}


def get_profile_values(params: Any, profile: int | None = None) -> dict[str, int]:
  profile = get_mpc_tuning_profile(params) if profile is None else profile
  if profile == MPC_PROFILE_CUSTOM:
    return _live_values(params)
  if profile not in MPC_PROFILES:
    raise ValueError(f"unknown MPC tuning profile: {profile}")

  values = dict(MPC_PROFILES[profile])
  saved = params.get(MPC_PROFILE_VALUE_PARAMS[profile])
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


def write_live_values(params: Any, values: dict[str, int], selected_profile: int | None = None) -> None:
  from openpilot.selfdrive.controls.lib.longitudinal_backends.tuning import (
    TuningSnapshot, load_snapshot, snapshot_from_legacy_values, tuning_transaction_lock, write_snapshot,
  )
  with tuning_transaction_lock():
    try:
      current = load_snapshot(params)
    except ValueError:
      current = None
    profile = get_mpc_tuning_profile(params) if selected_profile is None else selected_profile
    snapshot = snapshot_from_legacy_values(
      values, profile, revision=(current.revision + 1 if current is not None else 1),
    )
    if current is not None:
      snapshot = TuningSnapshot(snapshot.revision, snapshot.shared, snapshot.families, {
        slug: {**config, "profileId": profile,
               "overrides": {key: value for key, value in config.get("overrides", {}).items() if key.startswith("tn.")}}
        for slug, config in current.backends.items()
      })
    # Only touch compatibility keys after the complete new revision validates.
    if selected_profile is not None:
      params.put("MpcTuningProfile", selected_profile)
    for key in MPC_TUNING_KEYS:
      params.put(key, int(values[key]))
    write_snapshot(params, snapshot)


def save_profile_values(params: Any, profile: int, values: dict[str, int]) -> None:
  storage_key = MPC_PROFILE_VALUE_PARAMS.get(profile)
  if storage_key is not None:
    params.put(storage_key, {key: int(values[key]) for key in MPC_TUNING_KEYS})


def apply_profile(params: Any, profile: int) -> dict[str, int]:
  values = get_profile_values(params, profile)
  write_live_values(params, values, selected_profile=profile)
  return values
