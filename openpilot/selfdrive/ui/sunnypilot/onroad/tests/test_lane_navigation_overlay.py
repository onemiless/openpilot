from types import SimpleNamespace

from openpilot.selfdrive.ui.sunnypilot.onroad.lane_navigation_state import (
  lane_display_from_service,
  lane_display_from_ui_bridge,
  navigation_display_from_service,
  overlay_layout,
)
from openpilot.sunnypilot.lane_topology.types import LaneMarkingType


def test_lane_overlay_shows_markings_and_lane_position_when_control_is_observation_only():
  topology = SimpleNamespace(
    leftMarking="dashed",
    rightMarking="solid",
    egoLaneIndexFromLeft=1,
    visibleLaneCount=3,
    valid=True,
    stale=False,
    ambiguous=False,
    validForControl=False,
  )

  display = lane_display_from_service(topology, seen=True, alive=True, valid=True)

  assert display is not None
  assert display.left == "左侧  虚线"
  assert display.center == "当前 2 / 3 车道 · 仅显示"
  assert display.right == "右侧  实线"
  assert display.reliable


def test_lane_overlay_reports_uncertainty_instead_of_disappearing():
  topology = SimpleNamespace(
    leftMarking="unknown",
    rightMarking="solid",
    egoLaneIndexFromLeft=-1,
    visibleLaneCount=0,
    valid=False,
    stale=True,
    ambiguous=True,
    validForControl=False,
  )

  display = lane_display_from_service(topology, seen=True, alive=True, valid=True)

  assert display is not None
  assert display.left == "左侧  未知"
  assert display.right == "右侧  实线"
  assert display.center == "车道位置识别中 · 不确定"
  assert not display.reliable


def test_lane_overlay_uses_display_only_ui_bridge_when_track_service_is_absent():
  topology = SimpleNamespace(ego_lane_index_from_left=0, visible_lane_count=2, stale=False)

  display = lane_display_from_ui_bridge(topology, (LaneMarkingType.solid, LaneMarkingType.dashed))

  assert display is not None
  assert display.left == "左侧  实线"
  assert display.center == "当前 1 / 2 车道 · 仅显示"
  assert display.right == "右侧  虚线"
  assert display.reliable


def test_navigation_overlay_keeps_route_information_visible_while_control_waits_for_localization():
  nav = SimpleNamespace(
    maneuver="turnLeft",
    maneuverDistanceM=184,
    currentRoad="测试路",
    nextRoad="场地西路",
    lanes=[SimpleNamespace(index=1, recommended=True)],
    valid=False,
    rejectReason="phoneLocalization",
  )

  display = navigation_display_from_service(nav, seen=True, alive=True, valid=True)

  assert display is not None
  assert display.title == "←  184 m  左转"
  assert display.subtitle == "测试路  →  场地西路"
  assert display.detail == "等待手机定位 · 推荐第 2 车道"
  assert display.receiving
  assert not display.ready


def test_tici_overlay_layout_is_bounded_and_keeps_navigation_above_lane_pills():
  layout = overlay_layout(2160, 1080)
  nav_x, nav_y, nav_width, nav_height = layout.navigation
  left_x, lane_y, left_width, lane_height = layout.left_lane
  center_x, center_y, center_width, center_height = layout.center_lane
  right_x, right_y, right_width, right_height = layout.right_lane

  assert 0 <= nav_x and nav_x + nav_width <= 2160
  assert 0 <= left_x and right_x + right_width <= 2160
  assert nav_y + nav_height < lane_y
  assert lane_y == center_y == right_y
  assert lane_height == center_height == right_height
  assert left_x + left_width < center_x
  assert center_x + center_width < right_x
  assert lane_y + lane_height <= 1080
