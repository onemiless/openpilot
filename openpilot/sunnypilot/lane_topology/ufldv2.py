from __future__ import annotations

from collections.abc import Callable, Mapping
import math

import numpy as np

from openpilot.sunnypilot.lane_topology.image_marking import classify_marking_continuity
from openpilot.sunnypilot.lane_topology.types import LaneBoundaryObservation


UFLDV2_INPUT_WIDTH = 800
UFLDV2_INPUT_HEIGHT = 320
UFLDV2_RESIZED_HEIGHT = 400
UFLDV2_ROW_ANCHORS = np.linspace(160.0, 710.0, 56, dtype=np.float32) / 720.0


def _resize_bilinear_rgb(image: np.ndarray, output_width: int, output_height: int) -> np.ndarray:
  """Dependency-free half-pixel bilinear resize for an RGB image."""

  input_height, input_width = image.shape[:2]
  x = np.clip((np.arange(output_width, dtype=np.float32) + 0.5) * input_width / output_width - 0.5, 0.0, input_width - 1.0)
  y = np.clip((np.arange(output_height, dtype=np.float32) + 0.5) * input_height / output_height - 0.5, 0.0, input_height - 1.0)
  x0, y0 = np.floor(x).astype(np.int32), np.floor(y).astype(np.int32)
  x1, y1 = np.minimum(x0 + 1, input_width - 1), np.minimum(y0 + 1, input_height - 1)
  wx, wy = x - x0, y - y0

  top = image[y0[:, None], x0[None, :]].astype(np.float32) * (1.0 - wx)[None, :, None]
  top += image[y0[:, None], x1[None, :]].astype(np.float32) * wx[None, :, None]
  bottom = image[y1[:, None], x0[None, :]].astype(np.float32) * (1.0 - wx)[None, :, None]
  bottom += image[y1[:, None], x1[None, :]].astype(np.float32) * wx[None, :, None]
  return top * (1.0 - wy)[:, None, None] + bottom * wy[:, None, None]


def prepare_tusimple_rgb(image: np.ndarray) -> np.ndarray:
  """Apply the official TuSimple test transform and return normalized NCHW.

  The official loader resizes the complete image to 800x400, takes its bottom
  320 rows, and applies ImageNet normalization. Cropping the source at the
  equivalent 20% boundary first avoids an unnecessary 800x80 intermediate.
  """

  source = np.asarray(image)
  if source.ndim != 3 or source.shape[2] != 3:
    raise ValueError("UFLDv2 input must be an HxWx3 RGB image")
  if source.dtype != np.uint8:
    raise ValueError("UFLDv2 RGB input must use uint8 pixels")

  crop_top = int(round(source.shape[0] * (1.0 - UFLDV2_INPUT_HEIGHT / UFLDV2_RESIZED_HEIGHT)))
  cropped = source[crop_top:]
  resized = _resize_bilinear_rgb(cropped, UFLDV2_INPUT_WIDTH, UFLDV2_INPUT_HEIGHT)
  normalized = resized / 255.0
  normalized = (normalized - np.array((0.485, 0.456, 0.406), dtype=np.float32)) / np.array((0.229, 0.224, 0.225), dtype=np.float32)
  return np.ascontiguousarray(normalized.transpose(2, 0, 1)[None], dtype=np.float32)


def _softmax(values: np.ndarray, *, axis: int = -1) -> np.ndarray:
  shifted = values - np.max(values, axis=axis, keepdims=True)
  exponent = np.exp(shifted)
  return exponent / np.sum(exponent, axis=axis, keepdims=True)


def decode_tusimple_row_lanes(outputs: Mapping[str, np.ndarray], source_width: int, source_height: int, *,
                              local_width: int = 14, min_valid_points: int = 4) -> tuple[tuple[tuple[float, float], ...], ...]:
  """Decode the official four TuSimple row-lane heads into source pixels."""

  loc_row = np.asarray(outputs["loc_row"], dtype=np.float32)
  exist_row = np.asarray(outputs["exist_row"], dtype=np.float32)
  if loc_row.shape != (1, 100, 56, 4):
    raise ValueError(f"unexpected UFLDv2 loc_row shape: {loc_row.shape}")
  if exist_row.shape != (1, 2, 56, 4):
    raise ValueError(f"unexpected UFLDv2 exist_row shape: {exist_row.shape}")
  if source_width <= 0 or source_height <= 0:
    raise ValueError("source dimensions must be positive")

  max_indices = np.argmax(loc_row[0], axis=0)
  valid = np.argmax(exist_row[0], axis=0).astype(bool)
  lanes: list[tuple[tuple[float, float], ...]] = []
  for lane_index in range(loc_row.shape[3]):
    valid_indices = np.flatnonzero(valid[:, lane_index])
    if len(valid_indices) < min_valid_points:
      continue
    points: list[tuple[float, float]] = []
    for anchor_index in valid_indices:
      center = int(max_indices[anchor_index, lane_index])
      indices = np.arange(max(0, center - local_width), min(99, center + local_width) + 1)
      weights = _softmax(loc_row[0, indices, anchor_index, lane_index])
      grid_position = float(np.sum(weights * indices) + 0.5)
      u = grid_position / 99.0 * source_width
      v = float(UFLDV2_ROW_ANCHORS[anchor_index] * source_height)
      points.append((u, v))
    lanes.append(tuple(points))
  return tuple(lanes)


def row_outputs_to_observations(outputs: Mapping[str, np.ndarray], rgb: np.ndarray,
                                projector: Callable[[float, float], tuple[float, float] | None]) -> tuple[LaneBoundaryObservation, ...]:
  """Decode, classify and project TuSimple lane outputs into vehicle space."""

  height, width = rgb.shape[:2]
  pixel_lanes = decode_tusimple_row_lanes(outputs, width, height)
  exist_row = np.asarray(outputs["exist_row"], dtype=np.float32)[0]
  valid_slots = [lane_index for lane_index in range(exist_row.shape[2])
                 if np.count_nonzero(np.argmax(exist_row[:, :, lane_index], axis=0)) >= 4]
  observations: list[LaneBoundaryObservation] = []
  for source_id, pixel_points in zip(valid_slots, pixel_lanes, strict=True):
    vehicle_points = [point for u, v in pixel_points if (point := projector(u, v)) is not None and point[0] >= 0.0]
    vehicle_points.sort()
    if len(vehicle_points) < 4:
      continue
    existence_probability = _softmax(exist_row[:, :, source_id].T)[:, 1]
    lane_confidence = float(np.mean(existence_probability[existence_probability >= 0.5]))
    if not math.isfinite(lane_confidence):
      lane_confidence = 0.0
    observations.append(LaneBoundaryObservation(
      source_id=source_id,
      points=tuple(vehicle_points),
      marking_type=classify_marking_continuity(rgb, pixel_points),
      confidence=float(np.clip(lane_confidence, 0.0, 1.0)),
    ))
  observations.sort(key=lambda observation: observation.points[0][1], reverse=True)
  return tuple(observations)
