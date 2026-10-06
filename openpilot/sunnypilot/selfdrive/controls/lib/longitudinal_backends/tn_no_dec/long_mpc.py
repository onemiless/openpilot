from dataclasses import replace
import numpy as np
from openpilot.cereal import log
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_backends.tuning import follow_distance_for_personality

from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_backends.legacy_mpc.contract import (
  LongitudinalPlanSource as LongitudinalPlanSource,
  STOP_DISTANCE as STOP_DISTANCE,
  T_IDXS as T_IDXS,
  get_T_FOLLOW as get_T_FOLLOW,
  get_stopped_equivalence_factor as get_stopped_equivalence_factor,
)
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_backends.legacy_mpc.c_generated_code.acados_ocp_solver_pyx import (
  AcadosOcpSolverCython as PrimaryAcadosSolver,
)
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_backends.legacy_mpc.c_generated_code_fallback.acados_ocp_solver_pyx import (
  AcadosOcpSolverCython as FallbackAcadosSolver,
)
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_backends.legacy_mpc.long_mpc import LegacyCruiseLongitudinalMpc
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_backends.tn_no_dec.long_mpc_sp import LongitudinalMpcSP


class LongitudinalMpc(LegacyCruiseLongitudinalMpc, LongitudinalMpcSP):
  """Final rs408 TN MPC with the retained acceleration-controller hooks."""

  high_speed_comfort_enabled = True

  def __init__(self, dt):
    LongitudinalMpcSP.__init__(self)
    LegacyCruiseLongitudinalMpc.__init__(self, PrimaryAcadosSolver, FallbackAcadosSolver, dt)

  def _scale_legacy_jerk_cost(self, jerk_cost: float) -> float:
    return self.scale_jerk_cost(jerk_cost)

  def _apply_legacy_backend_params(self) -> None:
    self.apply_accel_limits()

  def _legacy_cruise_accel_max(self, stock_accel_max: float) -> float:
    return self.cruise_accel_max(stock_accel_max)

  def _save_backend_solution_status(self) -> None:
    self.save_solution_status()

  def update(self, radarstate, v_cruise, personality=log.LongitudinalPersonality.standard):
    tuning = self.runtime_tuning
    if not self.high_speed_comfort_enabled or v_cruise <= 0.0 or not (radarstate.leadOne.present or radarstate.leadTwo.present):
      return super().update(radarstate, v_cruise, personality)
    comfort = float(np.interp(self.x0[1], [15.0, 25.0],
                              [tuning.comfort_brake, min(tuning.comfort_brake, 1.8)]))
    v_ego = float(self.x0[1])
    weights = []
    if comfort < tuning.comfort_brake:
      following_gap = follow_distance_for_personality(personality, tuning) * v_ego + tuning.stop_distance
      for lead in (radarstate.leadOne, radarstate.leadTwo):
        if not lead.present:
          continue
        gap, v_lead = float(lead.dRel), float(lead.vLead)
        if not np.all(np.isfinite([gap, v_lead])) or min(gap, v_lead) < 0.0:
          weights.append(0.0)
          continue
        speed_difference = v_ego**2 - v_lead**2
        if speed_difference <= 0.0:
          continue
        original_gap = following_gap + speed_difference / (2 * tuning.comfort_brake)
        target_gap = following_gap + speed_difference / (2 * comfort)
        span = target_gap - original_gap
        weights.append(float(np.clip((gap-original_gap)/span, 0.0, 1.0)) if span > 0.0 else 0.0)
    comfort = tuning.comfort_brake + (comfort-tuning.comfort_brake) * min(weights, default=0.0)
    self.runtime_tuning = replace(tuning, comfort_brake=comfort)
    try:
      return super().update(radarstate, v_cruise, personality)
    finally:
      self.runtime_tuning = tuning
