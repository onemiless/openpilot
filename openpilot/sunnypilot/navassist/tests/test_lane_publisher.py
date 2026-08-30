from types import SimpleNamespace

import pytest

from openpilot.sunnypilot.lane_topology.metric_marking import MetricMarkingEvidence
from openpilot.sunnypilot.lane_topology.types import (
  LaneBoundary,
  LaneMarkingType,
  LaneSpace,
  LaneTopology,
  LaneTopologyState,
)
from openpilot.sunnypilot.navassist.lane_publisher import build_lane_topology_message


NOW_NS = 2_000_000_000


def evidence(marking_type, confidence=0.9):
  return MetricMarkingEvidence(marking_type, confidence, 20, 15, 0.75, 4, 3, 1.0, 3.0, 3, 2, 0.9)


def bridge(*, left=LaneMarkingType.dashed, right=LaneMarkingType.solid,
           raw_left=LaneMarkingType.dashed, raw_right=LaneMarkingType.solid,
           state=LaneTopologyState.normal, timestamp_ns=NOW_NS - 50_000_000):
  topology = LaneTopology(
    frame_id=10,
    timestamp_ns=timestamp_ns,
    boundaries=(
      LaneBoundary(1, ((5.0, 1.8), (40.0, 1.8)), left, 0.9),
      LaneBoundary(2, ((5.0, -1.8), (40.0, -1.8)), right, 0.85),
    ),
    spaces=(LaneSpace(1, 2, 3.6, 0.85),),
    marking_count_visible=2,
    boundary_count_visible=2,
    visible_lane_count=1,
    ego_lane_index_from_left=0,
    ego_lane_index_from_right=0,
    lanes_left_of_ego=0,
    lanes_right_of_ego=0,
    state=state,
    confidence=0.85,
  )
  return SimpleNamespace(
    current=topology,
    ego_source_ids=(1, 2),
    marking_evidence=[MetricMarkingEvidence.unknown(), evidence(raw_left), evidence(raw_right)],
    ego_marking_types=lambda: (left, right),
  )


def test_control_validity_requires_fresh_synchronized_known_evidence():
  message = build_lane_topology_message(
    bridge(), now_ns=NOW_NS, image_mono_time=NOW_NS - 100_000_000, image_frame_id=9,
    calibration_valid=True,
  )
  state = message.laneTopologyStateSP
  assert message.valid and state.valid and state.validForControl
  assert state.leftMarking == "dashed"
  assert state.rightMarking == "solid"
  assert state.leftMarkingConfidence == pytest.approx(0.9)


def test_unknown_current_evidence_immediately_fails_closed_even_if_tracker_remembers_dashed():
  message = build_lane_topology_message(
    bridge(raw_left=LaneMarkingType.unknown), now_ns=NOW_NS,
    image_mono_time=NOW_NS - 100_000_000, calibration_valid=True,
  )
  assert not message.laneTopologyStateSP.validForControl


def test_stale_ambiguous_source_change_or_bad_calibration_fail_closed():
  stale = build_lane_topology_message(
    bridge(), now_ns=NOW_NS, image_mono_time=NOW_NS - 500_000_001, calibration_valid=True,
  ).laneTopologyStateSP
  assert stale.stale and not stale.validForControl

  ambiguous = build_lane_topology_message(
    bridge(state=LaneTopologyState.ambiguous), now_ns=NOW_NS,
    image_mono_time=NOW_NS - 1, calibration_valid=True,
  ).laneTopologyStateSP
  assert ambiguous.ambiguous and not ambiguous.validForControl

  changed = build_lane_topology_message(
    bridge(), now_ns=NOW_NS, image_mono_time=NOW_NS - 1,
    calibration_valid=True, source_pair_changed=True,
  ).laneTopologyStateSP
  assert changed.sourcePairChanged and not changed.validForControl

  uncalibrated = build_lane_topology_message(
    bridge(), now_ns=NOW_NS, image_mono_time=NOW_NS - 1, calibration_valid=False,
  ).laneTopologyStateSP
  assert not uncalibrated.validForControl


def test_no_topology_publishes_invalid_stale_message():
  empty = SimpleNamespace(current=None)
  message = build_lane_topology_message(empty, now_ns=NOW_NS)
  assert not message.valid
  assert message.laneTopologyStateSP.stale
  assert not message.laneTopologyStateSP.validForControl
