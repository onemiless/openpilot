from types import SimpleNamespace

import pytest

from openpilot.sunnypilot.selfdrive.controls.lib.lane_change_blocker import lane_topology_change_blocks


def topology(*, left="unknown", right="unknown", left_valid=False, right_valid=False, control_valid=True):
  return SimpleNamespace(
    validForControl=control_valid,
    leftEvidenceValid=left_valid,
    rightEvidenceValid=right_valid,
    leftEgoSideMarking=left,
    rightEgoSideMarking=right,
  )


@pytest.mark.parametrize("marking", ("solid", "doubleSolid", "solidDashed", "roadEdge"))
def test_reliable_non_crossable_marking_blocks_its_side(marking):
  assert lane_topology_change_blocks(topology(left=marking, left_valid=True), healthy=True) == (True, False)
  assert lane_topology_change_blocks(topology(right=marking, right_valid=True), healthy=True) == (False, True)


@pytest.mark.parametrize("marking", ("unknown", "dashed", "doubleDashed"))
def test_unknown_and_crossable_markings_do_not_create_a_global_block(marking):
  assert lane_topology_change_blocks(
    topology(left=marking, right=marking, left_valid=True, right_valid=True), healthy=True,
  ) == (False, False)


def test_unhealthy_or_observation_only_topology_is_not_used_as_a_global_block():
  observed = topology(left="solid", right="solid", left_valid=True, right_valid=True)
  assert lane_topology_change_blocks(observed, healthy=False) == (False, False)
  assert lane_topology_change_blocks(
    topology(left="solid", right="solid", left_valid=True, right_valid=True, control_valid=False), healthy=True,
  ) == (False, False)
  assert lane_topology_change_blocks(topology(left="solid", right="solid"), healthy=True) == (False, False)
