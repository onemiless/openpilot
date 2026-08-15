from dataclasses import dataclass
from enum import Enum, IntEnum


class BackendId(IntEnum):
  OFFICIAL = 0
  EXPERIMENTAL = 1
  TN_NO_DEC = 2

  # Compatibility aliases for integrations written before the implementations
  # were given accurate user-facing names. The integer IDs remain stable.
  DEFAULT = OFFICIAL
  CRAZYMAX = EXPERIMENTAL
  SP_UPSTREAM_TUNABLE = OFFICIAL
  LOCAL = EXPERIMENTAL


class ParamLayer(Enum):
  SHARED = "shared"
  ALGORITHM_FAMILY = "algorithm_family"
  BACKEND_NATIVE = "backend_native"


class ApplyMode(Enum):
  HOT = "hot"
  HOT_RAMPED = "hot_ramped"
  SAFE_POINT = "safe_point"
  RESTART = "restart"
  BUILD = "build"


class Support(Enum):
  EXACT = "exact"
  ADAPTED = "adapted"
  UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class ParamSpec:
  id: str
  value_type: type
  unit: str
  default: int | float | bool
  minimum: int | float
  maximum: int | float
  step: int | float
  layer: ParamLayer
  apply_mode: ApplyMode
  min_update_s: float = 3.0
  ramp_rate: float | None = None
  expert: bool = False


@dataclass(frozen=True)
class ParamBinding:
  spec_id: str
  native_target: str
  support: Support = Support.EXACT


@dataclass(frozen=True)
class SolverContract:
  model_name: str
  generated_dir: str
  json_file: str
  x_dim: int
  u_dim: int
  param_dim: int
  horizon: int
  runtime_targets: frozenset[str]


@dataclass(frozen=True)
class BackendSpec:
  id: BackendId
  slug: str
  label: str
  planner_module: str
  algorithm_family: str | None
  bindings: tuple[ParamBinding, ...]
  capabilities: frozenset[str]
  solver: SolverContract
  control_policy_module: str | None = None
  experimental: bool = False


SHARED_PARAM_SPECS = (
  ParamSpec("following.time.relaxed_s", float, "s", 1.75, 0.50, 4.00, 0.01,
            ParamLayer.SHARED, ApplyMode.HOT_RAMPED, ramp_rate=0.20),
  ParamSpec("following.time.standard_s", float, "s", 1.45, 0.50, 4.00, 0.01,
            ParamLayer.SHARED, ApplyMode.HOT_RAMPED, ramp_rate=0.20),
  ParamSpec("following.time.aggressive_s", float, "s", 1.25, 0.50, 4.00, 0.01,
            ParamLayer.SHARED, ApplyMode.HOT_RAMPED, ramp_rate=0.20),
)


ACADOS_LONG_V1_PARAM_SPECS = (
  ParamSpec("mpc.obstacle_cost", float, "weight", 3.0, 0.01, 10.0, 0.01,
            ParamLayer.ALGORITHM_FAMILY, ApplyMode.HOT_RAMPED, ramp_rate=2.0, expert=True),
  ParamSpec("mpc.jerk_cost", float, "weight", 5.0, 0.01, 10.0, 0.01,
            ParamLayer.ALGORITHM_FAMILY, ApplyMode.HOT_RAMPED, ramp_rate=2.0, expert=True),
  ParamSpec("mpc.accel_change_cost", float, "weight", 200.0, 0.01, 500.0, 0.01,
            ParamLayer.ALGORITHM_FAMILY, ApplyMode.HOT_RAMPED, ramp_rate=100.0, expert=True),
  ParamSpec("mpc.danger_zone_cost", float, "weight", 100.0, 0.01, 500.0, 0.01,
            ParamLayer.ALGORITHM_FAMILY, ApplyMode.HOT_RAMPED, ramp_rate=100.0, expert=True),
  ParamSpec("mpc.lead_danger_factor", float, "ratio", 0.75, 0.01, 5.0, 0.01,
            ParamLayer.ALGORITHM_FAMILY, ApplyMode.HOT_RAMPED, ramp_rate=1.0, expert=True),
  ParamSpec("mpc.obstacle_comfort_brake_mps2", float, "m/s^2", 2.5, 0.50, 5.0, 0.01,
            ParamLayer.ALGORITHM_FAMILY, ApplyMode.HOT_RAMPED, ramp_rate=0.25),
  ParamSpec("mpc.obstacle_stop_distance_m", float, "m", 6.0, 1.0, 12.0, 0.01,
            ParamLayer.ALGORITHM_FAMILY, ApplyMode.HOT_RAMPED, ramp_rate=0.50),
  ParamSpec("mpc.jerk_factor.relaxed", float, "ratio", 1.0, 0.01, 3.0, 0.01,
            ParamLayer.ALGORITHM_FAMILY, ApplyMode.HOT_RAMPED, ramp_rate=1.0, expert=True),
)

TN_NATIVE_PARAM_SPECS = (
  ParamSpec("tn.accel_personality.enabled", bool, "bool", False, False, True, 1,
            ParamLayer.BACKEND_NATIVE, ApplyMode.HOT),
  ParamSpec("tn.accel_personality.profile", int, "enum", 1, 0, 2, 1,
            ParamLayer.BACKEND_NATIVE, ApplyMode.HOT),
)

PARAM_SPECS = SHARED_PARAM_SPECS + ACADOS_LONG_V1_PARAM_SPECS + TN_NATIVE_PARAM_SPECS
PARAM_SPECS_BY_ID = {spec.id: spec for spec in PARAM_SPECS}


COMMON_MPC_BINDINGS = (
  ParamBinding("following.time.relaxed_s", "t_follow_relaxed"),
  ParamBinding("following.time.standard_s", "t_follow_standard"),
  ParamBinding("following.time.aggressive_s", "t_follow_aggressive"),
  ParamBinding("mpc.obstacle_cost", "x_ego_obstacle_cost"),
  ParamBinding("mpc.jerk_cost", "j_ego_cost"),
  ParamBinding("mpc.accel_change_cost", "a_change_cost"),
  ParamBinding("mpc.danger_zone_cost", "danger_zone_cost"),
  ParamBinding("mpc.lead_danger_factor", "lead_danger_factor"),
  ParamBinding("mpc.obstacle_comfort_brake_mps2", "comfort_brake"),
  ParamBinding("mpc.obstacle_stop_distance_m", "stop_distance"),
  ParamBinding("mpc.jerk_factor.relaxed", "jerk_factor_standard"),
)

COMMON_RUNTIME_TARGETS = frozenset(binding.native_target for binding in COMMON_MPC_BINDINGS)
OFFICIAL_SOLVER = SolverContract("long", "c_generated_code", "acados_ocp_long.json",
                                 3, 1, 8, 12, COMMON_RUNTIME_TARGETS)
EXPERIMENTAL_SOLVER = SolverContract("long_official", "c_generated_code_official", "acados_ocp_long_official.json",
                                     3, 1, 8, 12, COMMON_RUNTIME_TARGETS)
TN_SOLVER = SolverContract("long_tn", "c_generated_code_tn", "acados_ocp_long_tn.json",
                           3, 1, 8, 12, COMMON_RUNTIME_TARGETS | {"accel_personality_enabled", "accel_personality_profile"})


BACKENDS = {
  BackendId.OFFICIAL: BackendSpec(
    id=BackendId.OFFICIAL,
    slug="sp_upstream_tunable",
    label="Official",
    planner_module="openpilot.selfdrive.controls.lib.longitudinal_planner_local",
    algorithm_family="acados_long_v1",
    bindings=COMMON_MPC_BINDINGS,
    capabilities=frozenset({"lead_mpc", "cruise_limiter", "standard_experimental_mode", "live_tuning"}),
    solver=OFFICIAL_SOLVER,
  ),
  BackendId.EXPERIMENTAL: BackendSpec(
    id=BackendId.EXPERIMENTAL,
    slug="local",
    label="Experimental",
    planner_module="openpilot.selfdrive.controls.lib.longitudinal_planner_official",
    algorithm_family="acados_long_v1",
    bindings=COMMON_MPC_BINDINGS,
    capabilities=frozenset({"cruise_mpc", "standard_experimental_mode", "live_tuning"}),
    solver=EXPERIMENTAL_SOLVER,
  ),
  BackendId.TN_NO_DEC: BackendSpec(
    id=BackendId.TN_NO_DEC,
    slug="tn_no_dec",
    label="TN-NoDEC",
    planner_module="openpilot.selfdrive.controls.lib.longitudinal_backends.tn_no_dec.planner",
    algorithm_family="acados_long_v1",
    bindings=COMMON_MPC_BINDINGS + (
      ParamBinding("tn.accel_personality.enabled", "accel_personality_enabled"),
      ParamBinding("tn.accel_personality.profile", "accel_personality_profile"),
    ),
    capabilities=frozenset({
      "cruise_mpc", "standard_experimental_mode", "accel_controller", "stop_hold",
      "departure_launch", "live_tuning",
    }),
    solver=TN_SOLVER,
    control_policy_module="openpilot.selfdrive.controls.lib.longitudinal_backends.tn_no_dec.longcontrol_policy",
    experimental=True,
  ),
}


def get_backend(mode: object) -> BackendSpec:
  try:
    backend_id = BackendId(int(mode))
  except (TypeError, ValueError):
    backend_id = BackendId.OFFICIAL
  return BACKENDS[backend_id]


def ordered_backends() -> tuple[BackendSpec, ...]:
  return tuple(BACKENDS[backend_id] for backend_id in sorted(BACKENDS))


def validate_registry() -> None:
  if len(PARAM_SPECS_BY_ID) != len(PARAM_SPECS):
    raise ValueError("duplicate longitudinal tuning parameter id")
  if len({backend.slug for backend in BACKENDS.values()}) != len(BACKENDS):
    raise ValueError("duplicate longitudinal backend slug")
  for spec in PARAM_SPECS:
    if spec.value_type not in (bool, int, float):
      raise ValueError(f"unsupported value type for {spec.id}")
    if spec.minimum > spec.default or spec.default > spec.maximum:
      raise ValueError(f"default outside bounds for {spec.id}")
    if spec.step <= 0 or spec.min_update_s < 0:
      raise ValueError(f"invalid update metadata for {spec.id}")
    if spec.apply_mode is ApplyMode.HOT_RAMPED and (spec.ramp_rate is None or spec.ramp_rate <= 0):
      raise ValueError(f"missing ramp rate for {spec.id}")
  for backend in BACKENDS.values():
    targets = [binding.native_target for binding in backend.bindings]
    if len(targets) != len(set(targets)):
      raise ValueError(f"duplicate native target for {backend.slug}")
    unknown = {binding.spec_id for binding in backend.bindings} - PARAM_SPECS_BY_ID.keys()
    if unknown:
      raise ValueError(f"unknown parameter bindings for {backend.slug}: {sorted(unknown)}")
    undeclared_targets = set(targets) - backend.solver.runtime_targets
    if undeclared_targets:
      raise ValueError(f"bindings outside solver contract for {backend.slug}: {sorted(undeclared_targets)}")
    if min(backend.solver.x_dim, backend.solver.u_dim, backend.solver.param_dim, backend.solver.horizon) <= 0:
      raise ValueError(f"invalid solver dimensions for {backend.slug}")


validate_registry()
