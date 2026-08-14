import json
import math
import fcntl
from contextlib import contextmanager
from dataclasses import replace
from dataclasses import dataclass
from typing import Any, Mapping

from openpilot.selfdrive.controls.lib.longitudinal_backends.registry import (
  ACADOS_LONG_V1_PARAM_SPECS, BACKENDS, PARAM_SPECS_BY_ID, SHARED_PARAM_SPECS, ApplyMode, BackendSpec,
)


CONFIG_PARAM = "LongitudinalTuningConfig"
STATE_PARAM = "LongitudinalTuningState"
MIGRATION_MARKER_PARAM = "LongitudinalTuningMigrated"
CONFIG_LOCK_PATH = "/tmp/longitudinal_tuning_config.lock"
SCHEMA_VERSION = 1

LEGACY_TO_SEMANTIC = {
  "MpcTFollowRelaxed": "following.time.relaxed_s",
  "MpcTFollowStandard": "following.time.standard_s",
  "MpcTFollowAggressive": "following.time.aggressive_s",
  "MpcXObstacleCost": "mpc.obstacle_cost",
  "MpcJerkCost": "mpc.jerk_cost",
  "MpcAccelChangeCost": "mpc.accel_change_cost",
  "MpcDangerZoneCost": "mpc.danger_zone_cost",
  "MpcLeadDangerFactor": "mpc.lead_danger_factor",
  "MpcComfortBrake": "mpc.obstacle_comfort_brake_mps2",
  "MpcStopDistance": "mpc.obstacle_stop_distance_m",
  # Historical key name is wrong: current MPC code applies this to relaxed personality.
  "MpcJerkFactorStandard": "mpc.jerk_factor.relaxed",
}


@dataclass(frozen=True)
class TuningSnapshot:
  revision: int
  shared: Mapping[str, int | float | bool]
  families: Mapping[str, Mapping[str, int | float | bool]]
  backends: Mapping[str, Mapping[str, Any]]

  def to_dict(self) -> dict[str, Any]:
    return {
      "schemaVersion": SCHEMA_VERSION,
      "revision": self.revision,
      "shared": dict(self.shared),
      "families": {key: dict(values) for key, values in self.families.items()},
      "backends": {key: dict(values) for key, values in self.backends.items()},
    }


@dataclass(frozen=True)
class ResolvedTuning:
  revision: int
  backend_slug: str
  values: Mapping[str, int | float | bool]
  native_values: Mapping[str, int | float | bool]


def default_snapshot(revision: int = 0) -> TuningSnapshot:
  return TuningSnapshot(
    revision=revision,
    shared={spec.id: spec.default for spec in SHARED_PARAM_SPECS},
    families={"acados_long_v1": {spec.id: spec.default for spec in ACADOS_LONG_V1_PARAM_SPECS}},
    backends={},
  )


def _validate_value(param_id: str, value: object) -> int | float | bool:
  spec = PARAM_SPECS_BY_ID[param_id]
  if spec.value_type is bool:
    if not isinstance(value, bool):
      raise ValueError(f"{param_id} must be bool")
    return value
  if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
    raise ValueError(f"{param_id} must be a finite number")
  value = spec.value_type(value)
  if not spec.minimum <= value <= spec.maximum:
    raise ValueError(f"{param_id} outside safety bounds")
  if spec.value_type is int:
    if value % spec.step:
      raise ValueError(f"{param_id} does not match quantization step")
  elif not math.isclose(round(value / spec.step) * spec.step, value, abs_tol=1e-9):
    raise ValueError(f"{param_id} does not match quantization step")
  return value


def _validate_values(values: object, allowed: set[str]) -> dict[str, int | float | bool]:
  if not isinstance(values, dict):
    raise ValueError("tuning values must be an object")
  unknown = set(values) - allowed
  if unknown:
    raise ValueError(f"unknown tuning parameters: {sorted(unknown)}")
  return {key: _validate_value(key, value) for key, value in values.items()}


def _validate_following_order(values: Mapping[str, int | float | bool]) -> None:
  relaxed = values.get("following.time.relaxed_s")
  standard = values.get("following.time.standard_s")
  aggressive = values.get("following.time.aggressive_s")
  if all(value is not None for value in (relaxed, standard, aggressive)) and not aggressive <= standard <= relaxed:
    raise ValueError("following times must satisfy aggressive <= standard <= relaxed")


def parse_snapshot(raw: object) -> TuningSnapshot:
  if isinstance(raw, bytes):
    raw = raw.decode()
  if isinstance(raw, str):
    try:
      raw = json.loads(raw)
    except json.JSONDecodeError as exc:
      raise ValueError("invalid longitudinal tuning JSON") from exc
  if not isinstance(raw, dict):
    raise ValueError("longitudinal tuning config must be an object")
  if raw.get("schemaVersion") != SCHEMA_VERSION:
    raise ValueError("unsupported longitudinal tuning schema")
  revision = raw.get("revision")
  if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
    raise ValueError("invalid longitudinal tuning revision")

  shared_ids = {spec.id for spec in SHARED_PARAM_SPECS}
  family_ids = {spec.id for spec in ACADOS_LONG_V1_PARAM_SPECS}
  shared = _validate_values(raw.get("shared", {}), shared_ids)
  _validate_following_order(shared)
  families_raw = raw.get("families", {})
  if not isinstance(families_raw, dict) or set(families_raw) - {"acados_long_v1"}:
    raise ValueError("unknown longitudinal tuning family")
  families = {
    "acados_long_v1": _validate_values(families_raw.get("acados_long_v1", {}), family_ids),
  }
  backends = raw.get("backends", {})
  if not isinstance(backends, dict) or any(not isinstance(value, dict) for value in backends.values()):
    raise ValueError("invalid backend tuning overrides")
  known_slugs = {backend.slug for backend in BACKENDS.values()}
  if set(backends) - known_slugs:
    raise ValueError(f"unknown longitudinal backends: {sorted(set(backends) - known_slugs)}")
  for backend_slug, backend_cfg in backends.items():
    overrides = backend_cfg.get("overrides", {})
    if not isinstance(overrides, dict):
      raise ValueError(f"invalid overrides for {backend_slug}")
    backend = next(candidate for candidate in BACKENDS.values() if candidate.slug == backend_slug)
    supported = {binding.spec_id for binding in backend.bindings}
    _validate_values(overrides, supported)
  snapshot = TuningSnapshot(revision=revision, shared=shared, families=families, backends=backends)
  for backend in BACKENDS.values():
    resolve_tuning(snapshot, backend)
  return snapshot


def load_snapshot(params: Any) -> TuningSnapshot | None:
  raw = params.get(CONFIG_PARAM)
  return None if not raw else parse_snapshot(raw)


def read_valid_revision(params: Any, last_known_good: int = 0) -> int:
  try:
    snapshot = load_snapshot(params)
  except ValueError:
    return last_known_good
  return snapshot.revision if snapshot is not None else 0


def write_snapshot(params: Any, snapshot: TuningSnapshot) -> None:
  params.put(CONFIG_PARAM, snapshot.to_dict(), block=True)


@contextmanager
def tuning_transaction_lock():
  with open(CONFIG_LOCK_PATH, "a") as lock_file:
    fcntl.flock(lock_file, fcntl.LOCK_EX)
    try:
      yield
    finally:
      fcntl.flock(lock_file, fcntl.LOCK_UN)


def write_backend_overrides(params: Any, backend: BackendSpec,
                            overrides: Mapping[str, int | float | bool]) -> TuningSnapshot:
  with tuning_transaction_lock():
    try:
      current = load_snapshot(params)
    except ValueError:
      current = None
    if current is None:
      current = snapshot_from_legacy(params)
    supported = {binding.spec_id for binding in backend.bindings}
    if set(overrides) - supported:
      raise ValueError(f"unsupported parameters for {backend.slug}: {sorted(set(overrides) - supported)}")
    validated = {key: _validate_value(key, value) for key, value in overrides.items()}
    backends = {slug: dict(config) for slug, config in current.backends.items()}
    backend_config = dict(backends.get(backend.slug, {}))
    backend_config["overrides"] = {**backend_config.get("overrides", {}), **validated}
    backends[backend.slug] = backend_config
    updated = TuningSnapshot(current.revision + 1, current.shared, current.families, backends)
    # Resolve before commit so unsupported/cross-field errors reject the whole revision.
    resolve_tuning(updated, backend)
    write_snapshot(params, updated)
    return updated


def snapshot_from_legacy_values(legacy: Mapping[str, int], profile: int, revision: int = 1,
                                backend_slugs: tuple[str, ...] = ("sp_upstream_tunable", "local", "tn_no_dec")) -> TuningSnapshot:
  semantic = {semantic_id: int(legacy[legacy_key]) / 100.0
              for legacy_key, semantic_id in LEGACY_TO_SEMANTIC.items()}
  shared_ids = {spec.id for spec in SHARED_PARAM_SPECS}
  family_ids = {spec.id for spec in ACADOS_LONG_V1_PARAM_SPECS}
  return TuningSnapshot(
    revision=revision,
    shared={key: _validate_value(key, value) for key, value in semantic.items() if key in shared_ids},
    families={"acados_long_v1": {
      key: _validate_value(key, value) for key, value in semantic.items() if key in family_ids
    }},
    backends={slug: {"profileId": profile, "overrides": {}} for slug in backend_slugs},
  )


def snapshot_from_legacy(params: Any,
                         backend_slugs: tuple[str, ...] = ("sp_upstream_tunable", "local", "tn_no_dec")) -> TuningSnapshot:
  from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.tuning_presets import get_mpc_tuning_profile, get_profile_values

  profile = get_mpc_tuning_profile(params)
  legacy = get_profile_values(params, profile)
  snapshot = snapshot_from_legacy_values(legacy, profile, backend_slugs=backend_slugs)
  # Legacy SP compiled these two values into its six-parameter solver. Preserve
  # that effective behavior on the migration revision; later V1 edits may tune them.
  if "sp_upstream_tunable" in snapshot.backends:
    backends = {slug: dict(config) for slug, config in snapshot.backends.items()}
    backends["sp_upstream_tunable"] = {**backends["sp_upstream_tunable"], "overrides": {
      "mpc.obstacle_comfort_brake_mps2": 2.5,
      "mpc.obstacle_stop_distance_m": 6.0,
    }}
    snapshot = TuningSnapshot(snapshot.revision, snapshot.shared, snapshot.families, backends)
  return snapshot


def migrate_legacy_config(params: Any) -> TuningSnapshot | None:
  """Create the atomic V1 snapshot once without deleting rollback keys."""
  try:
    existing = load_snapshot(params)
  except ValueError:
    return None
  if existing is not None:
    return existing
  if params.get_bool(MIGRATION_MARKER_PARAM):
    return None
  snapshot = snapshot_from_legacy(params)
  write_snapshot(params, snapshot)
  params.put_bool(MIGRATION_MARKER_PARAM, True)
  return snapshot


def resolve_tuning(snapshot: TuningSnapshot, backend: BackendSpec) -> ResolvedTuning:
  values: dict[str, int | float | bool] = {spec.id: spec.default for spec in PARAM_SPECS_BY_ID.values()}
  values.update(snapshot.shared)
  if backend.algorithm_family is not None:
    values.update(snapshot.families.get(backend.algorithm_family, {}))
  backend_cfg = snapshot.backends.get(backend.slug, {})
  overrides = backend_cfg.get("overrides", {})
  supported_ids = {binding.spec_id for binding in backend.bindings}
  unsupported = set(overrides) - supported_ids
  if unsupported:
    raise ValueError(f"unsupported parameters for {backend.slug}: {sorted(unsupported)}")
  values.update({key: _validate_value(key, value) for key, value in overrides.items()})
  _validate_following_order(values)
  native = {binding.native_target: values[binding.spec_id]
            for binding in backend.bindings if binding.support.value != "unsupported"}
  return ResolvedTuning(snapshot.revision, backend.slug, values, native)


def load_resolved_tuning(params: Any, backend: BackendSpec) -> ResolvedTuning | None:
  snapshot = load_snapshot(params)
  return None if snapshot is None else resolve_tuning(snapshot, backend)


def ramp_dataclass(current: Any, target: Any, backend: BackendSpec, dt: float) -> Any:
  """Move a frozen native tuning dataclass toward a validated target."""
  if dt <= 0:
    return current
  changes = {}
  for binding in backend.bindings:
    field = binding.native_target
    if not hasattr(current, field) or not hasattr(target, field):
      continue
    spec = PARAM_SPECS_BY_ID[binding.spec_id]
    old, new = getattr(current, field), getattr(target, field)
    if spec.apply_mode is not ApplyMode.HOT_RAMPED or old == new:
      changes[field] = new
      continue
    limit = spec.ramp_rate * dt
    changes[field] = old + max(-limit, min(limit, new - old))
  return replace(current, **changes)


def write_effective_state(params: Any, backend: BackendSpec, revision: int, current: Any, target: Any) -> None:
  values = {}
  for binding in backend.bindings:
    field = binding.native_target
    if not hasattr(current, field) or not hasattr(target, field):
      continue
    effective, requested = getattr(current, field), getattr(target, field)
    applied = effective == requested or (isinstance(effective, float) and math.isclose(effective, requested, abs_tol=1e-9))
    values[binding.spec_id] = {
      "requested": requested, "effective": effective,
      "unit": PARAM_SPECS_BY_ID[binding.spec_id].unit,
      "status": "applied" if applied else "ramping",
    }
  params.put(STATE_PARAM, {
    "schemaVersion": SCHEMA_VERSION, "backendId": int(backend.id), "backend": backend.slug,
    "requestedRevision": revision, "values": values,
  })
