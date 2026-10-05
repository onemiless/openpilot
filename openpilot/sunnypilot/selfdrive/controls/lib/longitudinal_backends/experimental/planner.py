from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_backends.experimental.long_mpc import LongitudinalMpc
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_backends.legacy_mpc.planner import LegacyLongitudinalPlanner


class LongitudinalPlanner(LegacyLongitudinalPlanner):
  """Experimental uses the shared legacy flow with the existing upstream DEC."""

  def __init__(self, CP, CP_SP, **kwargs):
    super().__init__(CP, CP_SP, mpc_factory=LongitudinalMpc, **kwargs)
    self.output_a_target = kwargs.get('init_a', 0.0)
