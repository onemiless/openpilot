"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.
"""
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.sunnypilot.widgets.list_view import option_item_sp, simple_button_item_sp
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.scroller_tici import Scroller


class MpcTuningLayout(Widget):
  def __init__(self, back_callback):
    super().__init__()
    self._back_callback = back_callback

    self.back_button = simple_button_item_sp(
      button_text=lambda: tr("← Back"), button_width=200, callback=self._back_callback)

    # Group 1: instant effect
    self.cruise_min_accel = option_item_sp(
      title=tr("Cruise Max Deceleration"), param="MpcCruiseMinAccel",
      min_value=-200, max_value=-50, value_change_step=5, use_float_scaling=True,
      label_callback=lambda v: f"{v / 100:.2f} m/s²",
      description=tr("修改后下一控制周期立即生效"))
    self.cruise_max_accel = option_item_sp(
      title=tr("Cruise Max Acceleration"), param="MpcCruiseMaxAccel",
      min_value=80, max_value=250, value_change_step=5, use_float_scaling=True,
      label_callback=lambda v: f"{v / 100:.2f} m/s²",
      description=tr("修改后下一控制周期立即生效"))
    self.lead_danger_factor = option_item_sp(
      title=tr("Lead Danger Factor"), param="MpcLeadDangerFactor",
      min_value=15, max_value=60, value_change_step=1, use_float_scaling=True,
      label_callback=lambda v: f"{v / 100:.2f}",
      description=tr("修改后下一控制周期立即生效"))
    self.min_x_lead_factor = option_item_sp(
      title=tr("Min Lead Distance Factor"), param="MpcMinXLeadFactor",
      min_value=30, max_value=80, value_change_step=1, use_float_scaling=True,
      label_callback=lambda v: f"{v / 100:.2f}",
      description=tr("修改后下一控制周期立即生效"))
    self.crash_distance = option_item_sp(
      title=tr("Crash Distance Threshold"), param="MpcCrashDistance",
      min_value=10, max_value=50, value_change_step=1, use_float_scaling=True,
      label_callback=lambda v: f"{v / 100:.2f} m",
      description=tr("修改后下一控制周期立即生效"))

    self.stop_line_decel = option_item_sp(
      title=tr("Stop Line Deceleration"), param="StopLineExtraDecel",
      min_value=10, max_value=80, value_change_step=5, use_float_scaling=True,
      label_callback=lambda v: f"{v / 100:.2f} m/s²",
      description=tr("修改后下一控制周期立即生效"))

    # Group 2: re-engage to apply
    self.comfort_brake = option_item_sp(
      title=tr("Comfort Brake"), param="MpcComfortBrake",
      min_value=150, max_value=400, value_change_step=5, use_float_scaling=True,
      label_callback=lambda v: f"{v / 100:.2f} m/s³",
      description=tr("退出纵向控制再开启后生效"))
    self.stop_distance = option_item_sp(
      title=tr("Stop Distance"), param="MpcStopDistance",
      min_value=200, max_value=800, value_change_step=10, use_float_scaling=True,
      label_callback=lambda v: f"{v / 100:.2f} m",
      description=tr("退出纵向控制再开启后生效"))
    self.x_obstacle_cost = option_item_sp(
      title=tr("Obstacle Distance Cost Weight"), param="MpcXObstacleCost",
      min_value=100, max_value=2000, value_change_step=10, use_float_scaling=True,
      label_callback=lambda v: f"{v / 100:.1f}",
      description=tr("退出纵向控制再开启后生效"))
    self.jerk_cost = option_item_sp(
      title=tr("Jerk Smoothness Weight"), param="MpcJerkCost",
      min_value=100, max_value=1000, value_change_step=10, use_float_scaling=True,
      label_callback=lambda v: f"{v / 100:.1f}",
      description=tr("退出纵向控制再开启后生效"))
    self.a_change_cost = option_item_sp(
      title=tr("Acceleration Change Penalty"), param="MpcAChangeCost",
      min_value=2000, max_value=50000, value_change_step=100, use_float_scaling=True,
      label_callback=lambda v: f"{v / 100:.1f}",
      description=tr("退出纵向控制再开启后生效"))
    self.danger_zone_cost = option_item_sp(
      title=tr("Danger Zone Penalty"), param="MpcDangerZoneCost",
      min_value=2000, max_value=50000, value_change_step=100, use_float_scaling=True,
      label_callback=lambda v: f"{v / 100:.1f}",
      description=tr("退出纵向控制再开启后生效"))
    self.limit_cost = option_item_sp(
      title=tr("Constraint Violation Penalty"), param="MpcLimitCost",
      min_value=100000, max_value=10000000, value_change_step=100000,
      label_callback=lambda v: f"{v / 1000000:.1f}×10⁶" if v >= 1000000 else f"{v / 1000:.0f}×10³",
      description=tr("退出纵向控制再开启后生效"))

    all_items = [self.back_button,
      self.cruise_min_accel, self.cruise_max_accel,
      self.lead_danger_factor, self.min_x_lead_factor, self.crash_distance,
      self.stop_line_decel,
      self.comfort_brake, self.stop_distance,
      self.x_obstacle_cost, self.jerk_cost, self.a_change_cost,
      self.danger_zone_cost, self.limit_cost]
    self._scroller = Scroller(all_items, line_separator=True, spacing=0)

  def _render(self, rect): self._scroller.render(rect)
  def show_event(self): self._scroller.show_event()
