from __future__ import annotations

from dataclasses import dataclass


MARKING_LABELS = {
  "solid": "实线",
  "dashed": "虚线",
  "doubleSolid": "双实线",
  "doubleDashed": "双虚线",
  "solidDashed": "实虚线",
  "roadEdge": "路缘",
  "unknown": "未知",
}

MANEUVER_LABELS = {
  "none": ("·", "等待指令"),
  "straight": ("↑", "直行"),
  "slightLeft": ("↖", "左前方"),
  "slightRight": ("↗", "右前方"),
  "turnLeft": ("←", "左转"),
  "turnRight": ("→", "右转"),
  "sharpLeft": ("↖", "急左转"),
  "sharpRight": ("↗", "急右转"),
  "uTurnLeft": ("↶", "左掉头"),
  "uTurnRight": ("↷", "右掉头"),
  "keepLeft": ("↖", "靠左行驶"),
  "keepRight": ("↗", "靠右行驶"),
  "mergeLeft": ("↖", "向左汇入"),
  "mergeRight": ("↗", "向右汇入"),
  "exitLeft": ("↖", "左侧出口"),
  "exitRight": ("↗", "右侧出口"),
  "rampLeft": ("↖", "进入左匝道"),
  "rampRight": ("↗", "进入右匝道"),
  "roundabout": ("↻", "进入环岛"),
  "destination": ("●", "到达目的地"),
  "unknown": ("·", "等待指令"),
}

REJECT_LABELS = {
  "none": "导航可用",
  "disabled": "导航未启用",
  "noData": "等待导航数据",
  "authentication": "等待手机连接",
  "malformed": "导航数据异常",
  "replay": "等待最新导航",
  "stale": "导航数据已过期",
  "routeUnmatched": "等待匹配路线",
  "gpsWeak": "GPS 信号弱",
  "localLocalization": "等待设备定位",
  "phoneLocalization": "等待手机定位",
  "outsideTrackDEPRECATED": "导航等待",
}


@dataclass(frozen=True)
class LaneOverlayDisplay:
  left: str
  center: str
  right: str
  left_marking: str = "unknown"
  right_marking: str = "unknown"
  reliable: bool = False


@dataclass(frozen=True)
class NavigationOverlayDisplay:
  title: str
  subtitle: str
  detail: str
  ready: bool = False
  receiving: bool = False
  linked: bool = False


@dataclass(frozen=True)
class OverlayLayout:
  navigation: tuple[float, float, float, float]
  left_lane: tuple[float, float, float, float]
  center_lane: tuple[float, float, float, float]
  right_lane: tuple[float, float, float, float]


def overlay_layout(width: float, height: float, *, bottom_inset: float = 24) -> OverlayLayout:
  nav_width = min(1120.0, max(640.0, width - 680.0))
  nav_height = 112.0
  lane_widths = (250.0, 320.0, 250.0)
  lane_gap = 16.0
  lane_height = 62.0
  lane_total = sum(lane_widths) + 2 * lane_gap
  lane_y = height - bottom_inset - lane_height
  nav_y = lane_y - 16.0 - nav_height
  nav_x = (width - nav_width) / 2
  lane_x = (width - lane_total) / 2
  return OverlayLayout(
    navigation=(nav_x, nav_y, nav_width, nav_height),
    left_lane=(lane_x, lane_y, lane_widths[0], lane_height),
    center_lane=(lane_x + lane_widths[0] + lane_gap, lane_y, lane_widths[1], lane_height),
    right_lane=(lane_x + lane_widths[0] + lane_gap + lane_widths[1] + lane_gap, lane_y, lane_widths[2], lane_height),
  )


def lane_display_from_service(topology, *, seen: bool, alive: bool, valid: bool) -> LaneOverlayDisplay | None:
  if not seen:
    return None
  if not alive or not valid:
    return LaneOverlayDisplay("左侧  未知", "车道线识别连接中", "右侧  未知")

  left_marking = str(topology.leftMarking)
  right_marking = str(topology.rightMarking)
  left = MARKING_LABELS.get(left_marking, "未知")
  right = MARKING_LABELS.get(right_marking, "未知")
  lane_index = int(topology.egoLaneIndexFromLeft)
  lane_count = int(topology.visibleLaneCount)
  reliable = bool(topology.valid and not topology.stale and not topology.ambiguous)
  center = f"当前 {lane_index + 1} / {lane_count} 车道" if lane_index >= 0 and lane_count > 0 else "车道线未知"
  if not reliable:
    center += " · 联动预览继续"
  elif topology.validForControl:
    center += " · 控制校验有效"
  else:
    center += " · 仅显示"
  return LaneOverlayDisplay(
    left=f"左侧  {left}",
    center=center,
    right=f"右侧  {right}",
    left_marking=left_marking,
    right_marking=right_marking,
    reliable=reliable,
  )


def lane_display_from_ui_bridge(topology, marking_types) -> LaneOverlayDisplay | None:
  if topology is None or marking_types is None:
    return None
  left_type, right_type = marking_types
  left_marking = getattr(left_type, "name", "unknown")
  right_marking = getattr(right_type, "name", "unknown")
  left = MARKING_LABELS.get(left_marking, "未知")
  right = MARKING_LABELS.get(right_marking, "未知")
  lane_index = int(topology.ego_lane_index_from_left)
  lane_count = int(topology.visible_lane_count)
  reliable = bool(not topology.stale and lane_index >= 0 and lane_count > 0)
  center = f"当前 {lane_index + 1} / {lane_count} 车道 · 仅显示" if reliable else "车道位置识别中 · 不确定"
  return LaneOverlayDisplay(
    left=f"左侧  {left}",
    center=center,
    right=f"右侧  {right}",
    left_marking=left_marking,
    right_marking=right_marking,
    reliable=reliable,
  )


def navigation_display_from_service(
  nav,
  *,
  seen: bool,
  alive: bool,
  valid: bool,
  lane_intent=None,
  lane_intent_healthy: bool = False,
  decel_active: bool = False,
) -> NavigationOverlayDisplay | None:
  if not seen:
    return None
  if not alive or not valid:
    return NavigationOverlayDisplay("手机导航连接中", "请保持手机与 tici 在同一局域网", "导航服务等待", receiving=False)

  symbol, maneuver = MANEUVER_LABELS.get(str(nav.maneuver), MANEUVER_LABELS["unknown"])
  distance = max(0, int(nav.maneuverDistanceM))
  distance_text = f"{distance / 1000:.1f} km" if distance >= 1000 else f"{distance} m"
  title = f"{symbol}  {distance_text}  {maneuver}"

  current_road = str(nav.currentRoad).strip()
  next_road = str(nav.nextRoad).strip()
  if current_road and next_road:
    subtitle = f"{current_road}  →  {next_road}"
  else:
    subtitle = next_road or current_road or "路线已接收"

  details: list[str] = []
  recommended = [str(int(lane.index) + 1) for lane in nav.lanes if lane.recommended]
  if recommended:
    details.append(f"推荐第 {','.join(recommended)} 车道")
  if lane_intent_healthy and lane_intent is not None and lane_intent.signalRequested:
    direction = "左" if str(lane_intent.direction) == "left" else "右"
    if int(lane_intent.targetLaneIndex) < 0:
      details.append(f"{direction}转灯已提前开启")
    elif lane_intent.laneChangeAuthorized:
      details.append(f"{direction}变道已授权")
    else:
      details.append(f"{direction}变道等待虚线/盲区")
  if decel_active:
    details.append("导航减速生效")

  ready = bool(nav.valid)
  reject_reason = str(nav.rejectReason)
  linked = bool(
    getattr(nav, "routeActive", False)
    and getattr(nav, "routeMatched", False)
    and not getattr(nav, "stale", True)
  )
  gps_diagnostic = {
    "gpsWeak": "手机 GPS 仅提示",
    "phoneLocalization": "手机 GPS 仅提示",
    "localLocalization": "设备 GPS 仅提示",
  }.get(reject_reason)
  if ready:
    status = "导航可用"
  elif linked and gps_diagnostic is not None:
    status = f"导航联动已接入 · {gps_diagnostic}"
  else:
    status = REJECT_LABELS.get(reject_reason, "导航等待")
  details.insert(0, status)
  return NavigationOverlayDisplay(title, subtitle, " · ".join(details), ready=ready, receiving=True, linked=linked)
