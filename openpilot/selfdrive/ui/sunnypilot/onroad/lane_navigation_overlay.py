from __future__ import annotations

import pyray as rl

from openpilot.selfdrive.ui.sunnypilot.onroad.lane_navigation_state import (
  LaneOverlayDisplay,
  NavigationOverlayDisplay,
  lane_display_from_service,
  lane_display_from_ui_bridge,
  navigation_display_from_service,
  overlay_layout,
)
from openpilot.system.ui.lib.application import FontWeight, gui_app
from openpilot.system.ui.lib.text_measure import measure_text_cached


class LaneNavigationOverlay:
  """Read-only onroad presentation for lane topology and mobile navigation."""

  def __init__(self):
    self._font_bold = gui_app.font(FontWeight.BOLD)
    self._font_semi_bold = gui_app.font(FontWeight.SEMI_BOLD)

  def render(self, rect: rl.Rectangle) -> None:
    # Keep the pure presentation helpers importable without constructing the
    # global UI state; the runtime singleton is needed only for actual drawing.
    from openpilot.selfdrive.ui.ui_state import ui_state

    sm = ui_state.sm
    paired = ui_state.nav_assist_track_mode
    lane_display = lane_display_from_service(
      sm["laneTopologyStateSP"],
      seen=sm.seen["laneTopologyStateSP"],
      alive=sm.alive["laneTopologyStateSP"],
      valid=sm.valid["laneTopologyStateSP"],
    )
    if lane_display is None:
      lane_display = lane_display_from_ui_bridge(
        ui_state.lane_topology,
        ui_state.lane_topology_bridge.ego_marking_types(),
      )
    nav_seen = sm.seen["navAssistStateSP"]
    nav_display = navigation_display_from_service(
      sm["navAssistStateSP"],
      seen=nav_seen,
      alive=sm.alive["navAssistStateSP"],
      valid=sm.valid["navAssistStateSP"],
      lane_intent=sm["navLaneIntentSP"],
      lane_intent_healthy=sm.seen["navLaneIntentSP"] and sm.alive["navLaneIntentSP"] and sm.valid["navLaneIntentSP"],
      decel_active=(sm.alive["longitudinalPlanSP"] and sm.valid["longitudinalPlanSP"] and
                    str(sm["longitudinalPlanSP"].longitudinalPlanSource) == "navAssist"),
    )

    if paired and lane_display is None:
      lane_display = LaneOverlayDisplay("左侧  未知", "车道线识别启动中", "右侧  未知")
    if paired and nav_display is None:
      nav_display = NavigationOverlayDisplay("等待手机导航", "在 TesNav 中选择路线并开始导航", "局域网连接等待")
    if lane_display is None and nav_display is None:
      return

    bottom_inset = 84.0 if int(ui_state.developer_ui or 0) in (1, 3) else 24.0
    layout = overlay_layout(rect.width, rect.height, bottom_inset=bottom_inset)
    if nav_display is not None:
      self._draw_navigation(self._offset(layout.navigation, rect), nav_display)
    if lane_display is not None:
      self._draw_lane_pill(self._offset(layout.left_lane, rect), lane_display.left, lane_display.left_marking, lane_display.reliable)
      self._draw_center_pill(self._offset(layout.center_lane, rect), lane_display.center, lane_display.reliable)
      self._draw_lane_pill(self._offset(layout.right_lane, rect), lane_display.right, lane_display.right_marking, lane_display.reliable)

  @staticmethod
  def _offset(values: tuple[float, float, float, float], rect: rl.Rectangle) -> rl.Rectangle:
    x, y, width, height = values
    return rl.Rectangle(rect.x + x, rect.y + y, width, height)

  def _draw_navigation(self, box: rl.Rectangle, display: NavigationOverlayDisplay) -> None:
    background = rl.Color(8, 16, 24, 188)
    accent = (rl.Color(75, 224, 164, 245) if display.ready else
              rl.Color(75, 190, 224, 240) if display.linked else
              rl.Color(255, 190, 74, 235) if display.receiving else
              rl.Color(170, 180, 190, 220))
    rl.draw_rectangle_rounded(box, 0.22, 10, background)
    rl.draw_rectangle_rounded_lines_ex(box, 0.22, 10, 2, rl.Color(accent.r, accent.g, accent.b, 100))
    rl.draw_rectangle_rounded(rl.Rectangle(box.x + 12, box.y + 12, 7, box.height - 24), 1.0, 6, accent)

    title = self._fit(display.title, box.width - 52, self._font_bold, 43)
    subtitle = self._fit(display.subtitle, box.width - 52, self._font_semi_bold, 29)
    detail = self._fit(display.detail, box.width - 52, self._font_semi_bold, 25)
    rl.draw_text_ex(self._font_bold, title, rl.Vector2(box.x + 34, box.y + 10), 43, 0, rl.Color(255, 255, 255, 245))
    rl.draw_text_ex(self._font_semi_bold, subtitle, rl.Vector2(box.x + 34, box.y + 55), 29, 0, rl.Color(235, 240, 244, 220))
    detail_size = measure_text_cached(self._font_semi_bold, detail, 25)
    rl.draw_text_ex(self._font_semi_bold, detail, rl.Vector2(box.x + box.width - detail_size.x - 20, box.y + 80),
                    25, 0, accent)

  def _draw_lane_pill(self, box: rl.Rectangle, text: str, marking: str, reliable: bool) -> None:
    color = self._marking_color(marking, reliable)
    rl.draw_rectangle_rounded(box, 0.45, 10, rl.Color(8, 16, 24, 178))
    rl.draw_rectangle_rounded_lines_ex(box, 0.45, 10, 2, rl.Color(color.r, color.g, color.b, 120))
    self._draw_centered(box, text, self._font_bold, 31, color)

  def _draw_center_pill(self, box: rl.Rectangle, text: str, reliable: bool) -> None:
    color = rl.Color(245, 248, 250, 235) if reliable else rl.Color(174, 184, 194, 220)
    rl.draw_rectangle_rounded(box, 0.45, 10, rl.Color(8, 16, 24, 178))
    self._draw_centered(box, self._fit(text, box.width - 24, self._font_semi_bold, 27), self._font_semi_bold, 27, color)

  @staticmethod
  def _marking_color(marking: str, reliable: bool) -> rl.Color:
    if not reliable:
      return rl.Color(174, 184, 194, 210)
    if marking in ("dashed", "doubleDashed"):
      return rl.Color(80, 226, 169, 245)
    if marking in ("solid", "doubleSolid", "solidDashed", "roadEdge"):
      return rl.Color(255, 199, 92, 245)
    return rl.Color(190, 200, 210, 220)

  @staticmethod
  def _draw_centered(box: rl.Rectangle, text: str, font: rl.Font, size: int, color: rl.Color) -> None:
    measured = measure_text_cached(font, text, size)
    rl.draw_text_ex(font, text, rl.Vector2(box.x + (box.width - measured.x) / 2, box.y + (box.height - measured.y) / 2),
                    size, 0, color)

  @staticmethod
  def _fit(text: str, max_width: float, font: rl.Font, size: int) -> str:
    if measure_text_cached(font, text, size).x <= max_width:
      return text
    candidate = text
    while len(candidate) > 1 and measure_text_cached(font, candidate + "…", size).x > max_width:
      candidate = candidate[:-1]
    return candidate + "…"
