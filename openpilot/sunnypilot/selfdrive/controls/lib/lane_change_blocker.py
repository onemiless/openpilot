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


class LaneChangeBoundaryBlocker:
  """Road-edge-style entry veto with a short clear grace after confirmed solid."""

  def __init__(self, *, clear_frames: int = 6):
    if clear_frames <= 0:
      raise ValueError("clear_frames must be positive")
    self.clear_frames = clear_frames
    self._remaining = [0, 0]

  def reset(self) -> None:
    self._remaining = [0, 0]

  def update(self, topology: object, *, healthy: bool) -> tuple[bool, bool]:
    immediate = lane_topology_change_blocks(topology, healthy=healthy)
    blocked = [False, False]
    for side, detected in enumerate(immediate):
      if detected:
        self._remaining[side] = self.clear_frames
      elif self._remaining[side] > 0:
        self._remaining[side] -= 1
      blocked[side] = detected or self._remaining[side] > 0
    return blocked[0], blocked[1]
