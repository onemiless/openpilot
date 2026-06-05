from openpilot.selfdrive.ui.widgets.can_monitor import CanMonitorWidget
from openpilot.system.ui.widgets import Widget

class CanDashboardLayout(Widget):
  def __init__(self):
    super().__init__()
    self._monitor = CanMonitorWidget()

  def _render(self, rect):
    self._monitor.render(rect)
