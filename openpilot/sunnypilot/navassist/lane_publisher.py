from __future__ import annotations

from openpilot.cereal import messaging
from openpilot.sunnypilot.lane_topology.types import LaneMarkingType, LaneTopologyState


MODEL_MAX_AGE_NS = 150_000_000
MARKING_MAX_AGE_NS = 500_000_000

MARKING_TO_CEREAL = {
  LaneMarkingType.unknown: "unknown",
  LaneMarkingType.solid: "solid",
  LaneMarkingType.dashed: "dashed",
  LaneMarkingType.doubleSolid: "doubleSolid",
  LaneMarkingType.doubleDashed: "doubleDashed",
  LaneMarkingType.solidDashed: "solidDashed",
  LaneMarkingType.roadEdge: "roadEdge",
}
TOPOLOGY_TO_CEREAL = {
  LaneTopologyState.normal: "normal",
  LaneTopologyState.mergingLeft: "mergingLeft",
  LaneTopologyState.mergingRight: "mergingRight",
  LaneTopologyState.splittingLeft: "splittingLeft",
  LaneTopologyState.splittingRight: "splittingRight",
  LaneTopologyState.ambiguous: "ambiguous",
  LaneTopologyState.stale: "stale",
}


def build_lane_topology_message(bridge, *, now_ns: int, image_mono_time: int = 0, image_frame_id: int = 0,
                                calibration_valid: bool = False, source_pair_changed: bool = False):
  message = messaging.new_message("laneTopologyStateSP")
  state = message.laneTopologyStateSP
  state.publishMonoTime = now_ns
  topology = bridge.current
  if topology is None:
    message.valid = False
    state.stale = True
    state.ambiguous = True
    state.topologyState = "stale"
    return message

  model_age_ns = now_ns - topology.timestamp_ns
  model_fresh = 0 <= model_age_ns <= MODEL_MAX_AGE_NS
  image_age_ns = now_ns - image_mono_time if image_mono_time else MARKING_MAX_AGE_NS + 1
  image_fresh = 0 <= image_age_ns <= MARKING_MAX_AGE_NS
  state.modelMonoTime = topology.timestamp_ns
  state.imageMonoTime = image_mono_time
  state.frameId = topology.frame_id
  state.imageFrameId = image_frame_id
  state.calibrationValid = calibration_valid
  state.topologyState = TOPOLOGY_TO_CEREAL[topology.state]
  state.visibleLaneCount = max(0, topology.visible_lane_count)
  state.egoLaneIndexFromLeft = topology.ego_lane_index_from_left
  state.egoLaneIndexFromRight = topology.ego_lane_index_from_right
  state.leftNeighborExists = topology.lanes_left_of_ego > 0
  state.rightNeighborExists = topology.lanes_right_of_ego > 0
  state.sourcePairChanged = source_pair_changed

  marking_types = bridge.ego_marking_types()
  left_type, right_type = marking_types or (LaneMarkingType.unknown, LaneMarkingType.unknown)
  state.leftMarking = MARKING_TO_CEREAL[left_type]
  state.rightMarking = MARKING_TO_CEREAL[right_type]
  state.leftEvidenceAgeMs = max(0.0, image_age_ns / 1e6)
  state.rightEvidenceAgeMs = max(0.0, image_age_ns / 1e6)

  raw_evidence_known = False
  if bridge.ego_source_ids is not None:
    left_source, right_source = bridge.ego_source_ids
    left_evidence = bridge.marking_evidence[left_source]
    right_evidence = bridge.marking_evidence[right_source]
    state.leftMarkingConfidence = left_evidence.confidence
    state.rightMarkingConfidence = right_evidence.confidence
    raw_evidence_known = LaneMarkingType.unknown not in (left_evidence.marking_type, right_evidence.marking_type)

  if topology.ego_lane_index_from_left >= 0:
    ego_space = topology.spaces[topology.ego_lane_index_from_left]
    by_track = {boundary.track_id: boundary for boundary in topology.boundaries}
    left_boundary = by_track.get(ego_space.left_track_id)
    right_boundary = by_track.get(ego_space.right_track_id)
    if left_boundary is not None:
      state.leftBoundaryConfidence = left_boundary.confidence
    if right_boundary is not None:
      state.rightBoundaryConfidence = right_boundary.confidence

  ambiguous = topology.state != LaneTopologyState.normal or topology.ego_lane_index_from_left < 0
  stale = bool(topology.stale or not model_fresh or not image_fresh)
  state.ambiguous = ambiguous
  state.stale = stale
  known_stable_markings = LaneMarkingType.unknown not in (left_type, right_type)
  state.validForControl = bool(
    calibration_valid and not stale and not ambiguous and not source_pair_changed
    and known_stable_markings and raw_evidence_known
  )
  state.valid = bool(model_fresh and not topology.stale)
  message.valid = True
  return message
