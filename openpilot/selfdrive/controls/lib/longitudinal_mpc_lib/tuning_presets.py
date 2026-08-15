import json
from typing import Any

from openpilot.selfdrive.controls.lib.longitudinal_backends.registry import BackendId, BackendSpec, get_backend
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.modes import get_longitudinal_planner_mode


MPC_PROFILE_DEFAULT = 0
MPC_PROFILE_CRAZYMAX = 1
MPC_PROFILE_CUSTOM = 2
MPC_PROFILE_LEGACY_CUSTOM = 3

MPC_PROFILE_LABELS = {
  MPC_PROFILE_DEFAULT: "Default",
  MPC_PROFILE_CRAZYMAX: "CrazyMax",
  MPC_PROFILE_CUSTOM: "Custom",
}

MPC_CUSTOM_VALUES_PARAM = "MpcTuningCustomValues"

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

# Separate objects let each planner's Default evolve independently.
MPC_EXPERIMENTAL_DEFAULT_VALUES = dict(MPC_OFFICIAL_VALUES)
MPC_TN_DEFAULT_VALUES = dict(MPC_OFFICIAL_VALUES)
MPC_DEFAULT_VALUES = {
  BackendId.OFFICIAL: MPC_OFFICIAL_VALUES,
  BackendId.EXPERIMENTAL: MPC_EXPERIMENTAL_DEFAULT_VALUES,
  BackendId.TN_NO_DEC: MPC_TN_DEFAULT_VALUES,
}

# Preserve the distinct legacy longitudinal preset that was exposed alongside
# the dev260628XL preset before the planner/profile UI was simplified. CrazyMax
# is a fixed parameter profile shared by all planners, not a planner backend.
MPC_CRAZYMAX_VALUES = {
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
}

MPC_PROFILES = {
  MPC_PROFILE_DEFAULT: MPC_OFFICIAL_VALUES,
  MPC_PROFILE_CRAZYMAX: MPC_CRAZYMAX_VALUES,
}

MPC_TUNING_KEYS = tuple(MPC_OFFICIAL_VALUES)
OFFICIAL_MPC_TUNING_KEYS = MPC_TUNING_KEYS


def get_selected_backend(params: Any) -> BackendSpec:
  return get_backend(get_longitudinal_planner_mode(params))


def _decode_json_object(raw: object) -> dict[str, Any]:
  if isinstance(raw, dict):
    return raw
  if isinstance(raw, (str, bytes)):
    try:
      decoded = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
      return {}
    return decoded if isinstance(decoded, dict) else {}
  return {}


def _validated_values(base: dict[str, int], raw: object) -> dict[str, int]:
  values = dict(base)
  for key, value in _decode_json_object(raw).items():
    if key in values:
      values[key] = int(value)
  return values


def _live_values(params: Any) -> dict[str, int]:
  return {key: int(params.get(key, return_default=True)) for key in MPC_TUNING_KEYS}


def _migrate_legacy_custom(params: Any) -> None:
  backend = get_selected_backend(params)
  saved = _decode_json_object(params.get(MPC_CUSTOM_VALUES_PARAM))
  if backend.slug not in saved:
    saved[backend.slug] = _live_values(params)
    params.put(MPC_CUSTOM_VALUES_PARAM, saved, block=True)
  params.put("MpcTuningProfile", MPC_PROFILE_CUSTOM, block=True)


def get_mpc_tuning_profile(params: Any) -> int:
  try:
    profile = int(params.get("MpcTuningProfile", return_default=True))
  except (TypeError, ValueError):
    profile = MPC_PROFILE_DEFAULT
  if profile == MPC_PROFILE_LEGACY_CUSTOM:
    _migrate_legacy_custom(params)
    return MPC_PROFILE_CUSTOM
  return profile if profile in MPC_PROFILE_LABELS else MPC_PROFILE_DEFAULT


def get_profile_values(params: Any, profile: int | None = None,
                       backend: BackendSpec | None = None) -> dict[str, int]:
  backend = backend or get_selected_backend(params)
  profile = get_mpc_tuning_profile(params) if profile is None else profile
  if profile == MPC_PROFILE_DEFAULT:
    return dict(MPC_DEFAULT_VALUES[backend.id])
  if profile == MPC_PROFILE_CRAZYMAX:
    return dict(MPC_CRAZYMAX_VALUES)
  if profile == MPC_PROFILE_CUSTOM:
    saved = _decode_json_object(params.get(MPC_CUSTOM_VALUES_PARAM))
    return _validated_values(MPC_DEFAULT_VALUES[backend.id], saved.get(backend.slug))
  raise ValueError(f"unknown MPC tuning profile: {profile}")


def write_live_values(params: Any, values: dict[str, int], selected_profile: int | None = None,
                      backend: BackendSpec | None = None) -> None:
  from openpilot.selfdrive.controls.lib.longitudinal_backends.tuning import (
    LEGACY_TO_SEMANTIC, TuningSnapshot, load_snapshot, resolve_tuning, snapshot_from_legacy,
    tuning_transaction_lock, write_snapshot,
  )
  backend = backend or get_selected_backend(params)
  profile = get_mpc_tuning_profile(params) if selected_profile is None else selected_profile
  legacy_values = {key: int(values[key]) for key in MPC_TUNING_KEYS}
  semantic_values = {LEGACY_TO_SEMANTIC[key]: value / 100.0 for key, value in legacy_values.items()}

  with tuning_transaction_lock():
    try:
      current = load_snapshot(params)
    except ValueError:
      current = None
    if current is None:
      current = snapshot_from_legacy(params)

    backends = {slug: dict(config) for slug, config in current.backends.items()}
    backend_config = dict(backends.get(backend.slug, {}))
    native_overrides = {
      key: value for key, value in backend_config.get("overrides", {}).items() if key.startswith("tn.")
    }
    backend_config.update({"profileId": profile, "overrides": {**native_overrides, **semantic_values}})
    backends[backend.slug] = backend_config
    updated = TuningSnapshot(current.revision + 1, current.shared, current.families, backends)
    resolve_tuning(updated, backend)

    if selected_profile is not None:
      params.put("MpcTuningProfile", profile, block=True)
    for key, value in legacy_values.items():
      params.put(key, value)
    write_snapshot(params, updated)


def save_profile_values(params: Any, profile: int, values: dict[str, int],
                        backend: BackendSpec | None = None) -> None:
  if profile != MPC_PROFILE_CUSTOM:
    return
  backend = backend or get_selected_backend(params)
  saved = _decode_json_object(params.get(MPC_CUSTOM_VALUES_PARAM))
  saved[backend.slug] = {key: int(values[key]) for key in MPC_TUNING_KEYS}
  params.put(MPC_CUSTOM_VALUES_PARAM, saved, block=True)


def apply_profile(params: Any, profile: int, backend: BackendSpec | None = None) -> dict[str, int]:
  backend = backend or get_selected_backend(params)
  values = get_profile_values(params, profile, backend)
  save_profile_values(params, profile, values, backend)
  write_live_values(params, values, selected_profile=profile, backend=backend)
  return values
