from __future__ import annotations


NON_CROSSABLE_EGO_MARKINGS = frozenset(("solid", "doubleSolid", "solidDashed", "roadEdge"))


def lane_topology_change_blocks(topology: object, *, healthy: bool) -> tuple[bool, bool]:
  """Return reliable per-side lane-boundary vetoes for SP lane-change entry."""

  if not healthy or not bool(topology.validForControl):  # type: ignore[attr-defined]
    return False, False
  left = bool(
    topology.leftEvidenceValid  # type: ignore[attr-defined]
    and str(topology.leftEgoSideMarking) in NON_CROSSABLE_EGO_MARKINGS  # type: ignore[attr-defined]
  )
  right = bool(
    topology.rightEvidenceValid  # type: ignore[attr-defined]
    and str(topology.rightEgoSideMarking) in NON_CROSSABLE_EGO_MARKINGS  # type: ignore[attr-defined]
  )
  return left, right
