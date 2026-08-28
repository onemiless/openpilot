from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable

from openpilot.sunnypilot.selfdrive.radar_lane.occupancy import (
  LANE_CENTER_MASK,
  LANE_LEFT_MASK,
  LANE_RIGHT_MASK,
  MAX_FORWARD_DISTANCE_M,
)


DISPLAY_LANE_ORDER = (LANE_LEFT_MASK, LANE_CENTER_MASK, LANE_RIGHT_MASK)
SIDE_LANE_ORDER = (LANE_LEFT_MASK, LANE_RIGHT_MASK)
RADAR_LANE_MAX_DRAW_DISTANCE_M = MAX_FORWARD_DISTANCE_M
M_TO_FT = 3.28084
MS_TO_KPH = 3.6
MS_TO_MPH = 2.2369363
LEAD_TWO_HIDE_DISTANCE_M = 3.0
LEAD_TWO_SHOW_DISTANCE_M = 5.0
LEAD_TWO_SAME_OBJECT_LATERAL_M = 1.5
LEAD_SPATIAL_MATCH_DISTANCE_M = 4.0
LEAD_SPATIAL_MATCH_LATERAL_M = 1.5
STATIC_WORLD_SPEED_MPS = 1.5
STATIC_SIDE_OFFSET_M = 2.2
STATIC_CLUTTER_LATERAL_BAND_M = 1.0
STATIC_CLUTTER_MIN_TARGETS = 3
STATIC_CLUTTER_MIN_SPAN_M = 15.0
ARS408_VEHICLE_OR_VRU_CLASSES = frozenset((1, 2, 3, 4, 5))
ARS408_NON_VEHICLE_CLASSES = frozenset((0, 6))
ARS408_STATIC_PROPERTIES = frozenset((1, 3, 5))
ARS408_CLASS_LABELS = {
  0: "目标",
  1: "小车",
  2: "货车",
  3: "行人",
  4: "摩托",
  5: "自行车",
  6: "宽目标",
}
DISPLAY_SWITCH_ADVANTAGE_M = 6.0


@dataclass
class _LaneDisplayState:
  target: Any


class LaneDisplayTargetStabilizer:
  """Keep adjacent-lane display identity stable without changing radar/control data."""
  def __init__(self) -> None:
    self._states: dict[int, _LaneDisplayState] = {}

  def reset(self) -> None:
    self._states.clear()

  @staticmethod
  def _should_switch(incumbent: Any, challenger: Any) -> bool:
    if challenger is None or int(challenger.trackId) == int(incumbent.trackId):
      return False
    incumbent_cut_in = bool(getattr(incumbent, "cutInCandidate", False))
    challenger_cut_in = bool(getattr(challenger, "cutInCandidate", False))
    if challenger_cut_in and not incumbent_cut_in:
      return True
    if challenger_cut_in and incumbent_cut_in:
      return _target_priority(challenger) < _target_priority(incumbent)
    return float(challenger.dRel) + DISPLAY_SWITCH_ADVANTAGE_M < float(incumbent.dRel)

  def update(self, targets: Iterable[Any],
             lane_order: tuple[int, ...] = SIDE_LANE_ORDER) -> tuple[Any, ...]:
    candidates = tuple(target for target in targets if bool(getattr(target, "present", False)))
    selected = []
    selected_ids: set[int] = set()

    for lane_mask in lane_order:
      lane_targets = [
        target for target in candidates
        if int(getattr(target, "laneMask", 0)) & lane_mask and int(target.trackId) not in selected_ids
      ]
      best = min(lane_targets, key=_target_priority) if lane_targets else None
      state = self._states.get(lane_mask)
      if state is not None and int(state.target.trackId) in selected_ids:
        self._states.pop(lane_mask, None)
        state = None

      if state is not None:
        incumbent = next(
          (target for target in lane_targets if int(target.trackId) == int(state.target.trackId)), None,
        )
        if incumbent is not None:
          chosen = best if self._should_switch(incumbent, best) else incumbent
        else:
          chosen = best
      else:
        chosen = best

      if chosen is None:
        self._states.pop(lane_mask, None)
        continue
      self._states[lane_mask] = _LaneDisplayState(chosen)
      selected.append(chosen)
      selected_ids.add(int(chosen.trackId))

    return tuple(selected)


def _target_priority(target: Any) -> tuple[bool, float, float, int]:
  cut_in = bool(getattr(target, "cutInCandidate", False))
  crossing_time = float(getattr(target, "timeToLaneCross", -1.0))
  if not cut_in or not math.isfinite(crossing_time) or crossing_time < 0.0:
    crossing_time = math.inf
  return not cut_in, crossing_time, float(target.dRel), int(target.trackId)


def select_lane_display_targets(targets: Iterable[Any],
                                lane_order: tuple[int, ...] = DISPLAY_LANE_ORDER) -> tuple[Any, ...]:
  """Select at most one unique, risk-prioritized target for each displayed lane."""
  candidates = tuple(target for target in targets if bool(getattr(target, "present", False)))
  selected = []
  selected_ids: set[int] = set()
  for lane_mask in lane_order:
    lane_targets = [
      target for target in candidates
      if int(getattr(target, "laneMask", 0)) & lane_mask and int(target.trackId) not in selected_ids
    ]
    if not lane_targets:
      continue
    target = min(lane_targets, key=_target_priority)
    selected.append(target)
    selected_ids.add(int(target.trackId))
  return tuple(selected)


def filter_static_side_clutter(targets: Iterable[Any], v_ego: float) -> tuple[Any, ...]:
  """Hide clear roadside clusters while preserving classified vehicles and VRUs."""
  candidates = tuple(target for target in targets if bool(getattr(target, "present", False)))
  clutter_ids: set[int] = set()
  for side in (-1.0, 1.0):
    stationary_side = []
    for target in candidates:
      d_path = float(getattr(target, "dPath", getattr(target, "yRel", 0.0)))
      absolute_speed = float(v_ego) + float(getattr(target, "vRel", 0.0))
      object_class = int(getattr(target, "objectClass", 7))
      dynamic_property = int(getattr(target, "dynamicProperty", 4))
      if object_class in ARS408_VEHICLE_OR_VRU_CLASSES:
        continue
      is_stationary_side = side * d_path > STATIC_SIDE_OFFSET_M and abs(absolute_speed) <= STATIC_WORLD_SPEED_MPS
      if is_stationary_side and dynamic_property in ARS408_STATIC_PROPERTIES:
        # Native radar classification is enough to reject an isolated static
        # road/line reflection; requiring a same-frame cluster allowed one
        # surviving point to become the adjacent-lane representative.
        clutter_ids.add(int(target.trackId))
        continue
      if (is_stationary_side and
          (object_class not in ARS408_NON_VEHICLE_CLASSES or dynamic_property in ARS408_STATIC_PROPERTIES)):
        stationary_side.append((target, d_path))

    for target, lateral in stationary_side:
      cluster = [
        other for other, other_lateral in stationary_side
        if abs(other_lateral - lateral) <= STATIC_CLUTTER_LATERAL_BAND_M
      ]
      if len(cluster) < STATIC_CLUTTER_MIN_TARGETS:
        continue
      distances = [float(other.dRel) for other in cluster]
      if max(distances) - min(distances) >= STATIC_CLUTTER_MIN_SPAN_M:
        clutter_ids.update(int(other.trackId) for other in cluster)

  return tuple(target for target in candidates if int(target.trackId) not in clutter_ids)


def should_render_second_lead(lead_one: Any | None, lead_two: Any | None, was_visible: bool) -> bool:
  if lead_two is None or not bool(getattr(lead_two, "present", False)):
    return False
  if lead_one is None or not bool(getattr(lead_one, "present", False)):
    return True

  lead_one_id = int(getattr(lead_one, "radarTrackId", -1))
  lead_two_id = int(getattr(lead_two, "radarTrackId", -1))
  both_radar = bool(getattr(lead_one, "radar", False)) and bool(getattr(lead_two, "radar", False))
  if both_radar and lead_one_id >= 0 and lead_one_id == lead_two_id:
    return False

  lateral_separation = abs(float(getattr(lead_one, "yRel", 0.0)) - float(getattr(lead_two, "yRel", 0.0)))
  if lateral_separation > LEAD_TWO_SAME_OBJECT_LATERAL_M:
    return True

  longitudinal_separation = abs(float(lead_one.dRel) - float(lead_two.dRel))
  threshold = LEAD_TWO_HIDE_DISTANCE_M if was_visible else LEAD_TWO_SHOW_DISTANCE_M
  return longitudinal_separation > threshold


def rendered_radar_track_ids(radar_state: Any | None, include_lead_two: bool = True) -> frozenset[int]:
  if radar_state is None:
    return frozenset()
  track_ids = set()
  leads = (radar_state.leadOne, radar_state.leadTwo) if include_lead_two else (radar_state.leadOne,)
  for lead in leads:
    track_id = int(getattr(lead, "radarTrackId", -1))
    if bool(getattr(lead, "present", False)) and bool(getattr(lead, "radar", False)) and track_id >= 0:
      track_ids.add(track_id)
  return frozenset(track_ids)


def matches_rendered_lead(target: Any, radar_state: Any | None, include_lead_two: bool = True) -> bool:
  if radar_state is None:
    return False
  leads = (radar_state.leadOne, radar_state.leadTwo) if include_lead_two else (radar_state.leadOne,)
  target_id = int(getattr(target, "trackId", -1))
  for lead in leads:
    if not bool(getattr(lead, "present", False)):
      continue
    lead_id = int(getattr(lead, "radarTrackId", -1))
    if bool(getattr(lead, "radar", False)) and target_id >= 0 and target_id == lead_id:
      return True
    if (abs(float(target.dRel) - float(lead.dRel)) <= LEAD_SPATIAL_MATCH_DISTANCE_M and
        abs(float(target.yRel) - float(lead.yRel)) <= LEAD_SPATIAL_MATCH_LATERAL_M):
      return True
  return False


def format_target_label(d_rel: float, v_rel: float, v_ego: float, metric: bool,
                        object_class: int = 7) -> str:
  """Format distance and estimated longitudinal target speed for the overlay."""
  target_speed = v_ego + v_rel
  class_label = ARS408_CLASS_LABELS.get(int(object_class), "")
  prefix = f"{class_label}  " if class_label else ""
  if metric:
    return f"{prefix}{d_rel:.0f}m  {target_speed * MS_TO_KPH:.0f}km/h"
  return f"{prefix}{d_rel * M_TO_FT:.0f}ft  {target_speed * MS_TO_MPH:.0f}mph"
