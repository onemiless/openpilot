from openpilot.common.realtime import DT_MDL
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_backends.legacy_mpc.planner import LegacyLongitudinalPlanner
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_backends.tn_no_dec.long_mpc import LongitudinalMpc
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_backends.tn_no_dec.planner_sp import LongitudinalPlannerSP


class LongitudinalPlanner(LegacyLongitudinalPlanner, LongitudinalPlannerSP):
  """Retain TN-NoDEC policies around the single shared legacy planner flow."""
  log_fcw = True

  def __init__(self, CP, CP_SP, init_v=0.0, init_a=0.0, dt=DT_MDL):
    super().__init__(CP, CP_SP, mpc_factory=LongitudinalMpc, init_v=init_v, init_a=init_a, dt=dt)

  def _init_backend(self, CP, CP_SP, mpc, dt):
    LongitudinalPlannerSP.__init__(self, CP, CP_SP, mpc, dt=dt)

  def _prepare_mpc(self, sm, v_cruise, prev_accel_constraint, stock_accel_max, reset_state):
    is_e2e, v_cruise = self.update_accel_controller(sm, v_cruise, prev_accel_constraint, stock_accel_max, reset_state)
    return is_e2e, v_cruise, self.mpc_accel_seed

  def _final_should_stop(self, should_stop):
    return self.update_should_stop(should_stop)
