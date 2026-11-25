from openpilot.cereal import custom
from openpilot.sunnypilot.selfdrive.controls.lib.dec.dec import DynamicExperimentalController
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_backends.experimental.long_mpc import LongitudinalMpc
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_backends.legacy_mpc.planner import LegacyLongitudinalPlanner


class LongitudinalPlanner(LegacyLongitudinalPlanner):
  """Retain legacy DEC around the shared legacy planner flow."""

  def __init__(self, CP, CP_SP, **kwargs):
    super().__init__(CP, CP_SP, mpc_factory=LongitudinalMpc, **kwargs)
    self.output_a_target = kwargs.get('init_a', 0.0)

  def _init_backend(self, CP, CP_SP, mpc, dt):
    super()._init_backend(CP, CP_SP, mpc, dt)
    self.dec = DynamicExperimentalController(CP, mpc)

  def is_e2e(self, sm) -> bool:
    experimental_mode = sm['selfdriveState'].experimentalMode
    if not self.dec.active():
      return experimental_mode
    return experimental_mode and self.dec.mode() == "blended"

  def _update_backend(self, sm) -> None:
    self.dec.update(sm)

  def _publish_backend_state(self, longitudinal_plan_sp) -> None:
    dec_state = custom.LongitudinalPlanSP.DynamicExperimentalControl.DynamicExperimentalControlState
    dec = longitudinal_plan_sp.dec
    dec.state = dec_state.blended if self.dec.mode() == 'blended' else dec_state.acc
    dec.enabled = self.dec.enabled()
    dec.active = self.dec.active()
