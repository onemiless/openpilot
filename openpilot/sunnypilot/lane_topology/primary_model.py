from __future__ import annotations

from collections.abc import Callable, Iterable
import math
from typing import Protocol

from openpilot.sunnypilot.lane_topology.adapter import LaneTopologyFrame
from openpilot.sunnypilot.lane_topology.types import LaneBoundaryObservation, LaneMarkingType


MarkingClassifier = Callable[[int, object], LaneMarkingType]


class LaneLineLike(Protocol):
  x: Iterable[float]
  y: Iterable[float]


class ModelV2Like(Protocol):
  laneLines: Iterable[LaneLineLike]
  laneLineProbs: Iterable[float]


def model_v2_to_observations(model_v2: ModelV2Like, *, confidence_threshold: float = 0.35,
                             marking_classifier: MarkingClassifier | None = None,
                             max_distance_m: float = 80.0) -> tuple[LaneBoundaryObservation, ...]:
  """Reuse modelV2's four lane lines without running another neural network.

  This adapter is deliberately duck-typed so it works with both Cap'n Proto
  readers and small replay fixtures. It does not mutate modelV2 and has no
  dependency on messaging, GPU, camera, planner, or control code.
  """

  lane_lines = tuple(model_v2.laneLines)
  probabilities = tuple(float(value) for value in model_v2.laneLineProbs)
  if len(lane_lines) != 4 or len(probabilities) != 4:
    raise ValueError("primary model lane topology requires exactly four lane lines and probabilities")
  if not 0.0 <= confidence_threshold <= 1.0:
    raise ValueError("confidence_threshold must be within [0, 1]")

  observations: list[LaneBoundaryObservation] = []
  for source_id, (lane_line, confidence) in enumerate(zip(lane_lines, probabilities, strict=True)):
    if not math.isfinite(confidence) or confidence < confidence_threshold:
      continue
    xs = tuple(lane_line.x)
    ys = tuple(lane_line.y)
    if len(xs) != len(ys):
      raise ValueError(f"lane line {source_id} has mismatched x/y lengths")
    points = tuple((float(x), float(y)) for x, y in zip(xs, ys, strict=True)
                   if math.isfinite(x) and math.isfinite(y) and 0.0 <= x <= max_distance_m)
    if len(points) < 2:
      continue
    marking_type = marking_classifier(source_id, lane_line) if marking_classifier is not None else LaneMarkingType.unknown
    observations.append(LaneBoundaryObservation(
      source_id=source_id,
      points=points,
      marking_type=marking_type,
      confidence=min(confidence, 1.0),
    ))
  return tuple(observations)


class PrimaryModelLaneTopologyAdapter:
  """Shadow adapter for already-published modelV2 data; owns no GPU resources."""

  def __init__(self, *, confidence_threshold: float = 0.35,
               marking_classifier: MarkingClassifier | None = None):
    self.confidence_threshold = confidence_threshold
    self.marking_classifier = marking_classifier

  def infer(self, frame: LaneTopologyFrame) -> tuple[LaneBoundaryObservation, ...]:
    return model_v2_to_observations(frame.payload, confidence_threshold=self.confidence_threshold,  # type: ignore[arg-type]
                                    marking_classifier=self.marking_classifier)

  def close(self) -> None:
    pass
