from __future__ import annotations

from collections.abc import Callable

import numpy as np

from openpilot.sunnypilot.lane_topology.types import LaneBoundaryObservation
from openpilot.sunnypilot.lane_topology.ufldv2 import _resize_bilinear_rgb, classify_marking_continuity


UFLDV1_INPUT_WIDTH = 800
UFLDV1_INPUT_HEIGHT = 288
UFLDV1_GRID_COUNT = 100
UFLDV1_ROW_ANCHORS = np.arange(64, 285, 4, dtype=np.float32)


def prepare_tusimple_v1_rgb(image: np.ndarray) -> np.ndarray:
  source = np.asarray(image)
  if source.ndim != 3 or source.shape[2] != 3:
    raise ValueError("UFLDv1 input must be an HxWx3 RGB image")
  if source.dtype != np.uint8:
    raise ValueError("UFLDv1 RGB input must use uint8 pixels")
  resized = _resize_bilinear_rgb(source, UFLDV1_INPUT_WIDTH, UFLDV1_INPUT_HEIGHT) / 255.0
  normalized = (resized - np.array((0.485, 0.456, 0.406), dtype=np.float32)) / np.array((0.229, 0.224, 0.225), dtype=np.float32)
  return np.ascontiguousarray(normalized.transpose(2, 0, 1)[None], dtype=np.float32)


def decode_tusimple_v1(logits: np.ndarray, source_width: int, source_height: int, *,
                       min_valid_points: int = 3) -> tuple[tuple[tuple[float, float], ...], ...]:
  output = np.asarray(logits, dtype=np.float32)
  if output.shape != (1, 101, 56, 4):
    raise ValueError(f"unexpected UFLDv1 output shape: {output.shape}")
  if source_width <= 0 or source_height <= 0:
    raise ValueError("source dimensions must be positive")

  lane_logits = output[0]
  shifted = lane_logits[:-1] - np.max(lane_logits[:-1], axis=0, keepdims=True)
  probabilities = np.exp(shifted)
  probabilities /= np.sum(probabilities, axis=0, keepdims=True)
  grid_indices = np.arange(1, UFLDV1_GRID_COUNT + 1, dtype=np.float32)[:, None, None]
  locations = np.sum(probabilities * grid_indices, axis=0)
  locations[np.argmax(lane_logits, axis=0) == UFLDV1_GRID_COUNT] = 0.0

  column_step = (UFLDV1_INPUT_WIDTH - 1) / (UFLDV1_GRID_COUNT - 1)
  lanes: list[tuple[tuple[float, float], ...]] = []
  for lane_index in range(locations.shape[1]):
    valid_anchors = np.flatnonzero(locations[:, lane_index] > 0.0)
    if len(valid_anchors) < min_valid_points:
      continue
    points = tuple(
      (float(locations[anchor, lane_index] * column_step * source_width / UFLDV1_INPUT_WIDTH - 1.0),
       float(source_height * UFLDV1_ROW_ANCHORS[anchor] / UFLDV1_INPUT_HEIGHT - 1.0))
      for anchor in valid_anchors
    )
    lanes.append(points)
  return tuple(lanes)


def v1_logits_to_observations(logits: np.ndarray, rgb: np.ndarray,
                              projector: Callable[[float, float], tuple[float, float] | None]) -> tuple[LaneBoundaryObservation, ...]:
  height, width = rgb.shape[:2]
  pixel_lanes = decode_tusimple_v1(logits, width, height)
  observations: list[LaneBoundaryObservation] = []
  for source_id, pixel_points in enumerate(pixel_lanes):
    vehicle_points = [point for u, v in pixel_points if (point := projector(u, v)) is not None and point[0] >= 0.0]
    vehicle_points.sort()
    if len(vehicle_points) < 3:
      continue
    observations.append(LaneBoundaryObservation(
      source_id=source_id,
      points=tuple(vehicle_points),
      marking_type=classify_marking_continuity(rgb, pixel_points),
      confidence=1.0,
    ))
  observations.sort(key=lambda observation: observation.points[0][1], reverse=True)
  return tuple(observations)
