import numpy as np
import pytest

from openpilot.sunnypilot.lane_topology.types import LaneMarkingType
from openpilot.sunnypilot.lane_topology.image_marking import classify_marking_continuity
from openpilot.sunnypilot.lane_topology.ufldv2 import (
  _resize_bilinear_rgb,
  decode_tusimple_row_lanes,
  prepare_tusimple_rgb,
  row_outputs_to_observations,
)


def synthetic_outputs(*, lane_slot: int = 1, grid_index: int = 50, valid_count: int = 8):
  loc_row = np.full((1, 100, 56, 4), -8.0, dtype=np.float32)
  exist_row = np.full((1, 2, 56, 4), -8.0, dtype=np.float32)
  loc_col = np.zeros((1, 100, 41, 4), dtype=np.float32)
  exist_col = np.zeros((1, 2, 41, 4), dtype=np.float32)
  loc_row[0, grid_index, -valid_count:, lane_slot] = 8.0
  exist_row[0, 1, -valid_count:, lane_slot] = 8.0
  exist_row[0, 0, :-valid_count, lane_slot] = 8.0
  return {"loc_row": loc_row, "loc_col": loc_col, "exist_row": exist_row, "exist_col": exist_col}


def test_dependency_free_resize_preserves_constant_rgb():
  image = np.full((7, 11, 3), (10, 20, 30), dtype=np.uint8)
  resized = _resize_bilinear_rgb(image, 5, 3)
  assert resized.shape == (3, 5, 3)
  np.testing.assert_allclose(resized, np.broadcast_to((10, 20, 30), resized.shape))


def test_prepare_tusimple_rgb_matches_shape_and_normalization_contract():
  image = np.zeros((720, 1280, 3), dtype=np.uint8)
  prepared = prepare_tusimple_rgb(image)
  assert prepared.shape == (1, 3, 320, 800)
  assert prepared.dtype == np.float32
  np.testing.assert_allclose(prepared[0, :, 0, 0], -np.array((0.485, 0.456, 0.406)) / np.array((0.229, 0.224, 0.225)))


def test_decode_tusimple_row_lane_uses_source_dimensions():
  lanes = decode_tusimple_row_lanes(synthetic_outputs(), 1280, 720)
  assert len(lanes) == 1
  assert len(lanes[0]) == 8
  assert lanes[0][-1][0] == pytest.approx((50.5 / 99.0) * 1280, abs=0.01)
  assert lanes[0][-1][1] == pytest.approx(710.0, abs=0.01)


def test_decoder_rejects_wrong_output_shape():
  outputs = synthetic_outputs()
  outputs["loc_row"] = np.zeros((1, 99, 56, 4), dtype=np.float32)
  with pytest.raises(ValueError, match="loc_row"):
    decode_tusimple_row_lanes(outputs, 1280, 720)


def test_marking_continuity_distinguishes_solid_and_dashed():
  points = tuple((60.0, float(v)) for v in range(20, 101, 8))
  solid = np.full((120, 120, 3), 30, dtype=np.uint8)
  solid[:, 58:63] = 240
  assert classify_marking_continuity(solid, points) == LaneMarkingType.solid

  dashed = np.full((120, 120, 3), 30, dtype=np.uint8)
  for index, (_, v) in enumerate(points):
    if index % 2 == 0:
      center = int(v)
      dashed[center - 3:center + 4, 58:63] = 240
  assert classify_marking_continuity(dashed, points) == LaneMarkingType.dashed


def test_observations_project_without_touching_control_contracts():
  image = np.full((720, 1280, 3), 30, dtype=np.uint8)
  outputs = synthetic_outputs(valid_count=8)
  observations = row_outputs_to_observations(outputs, image, lambda u, v: (720.0 - v, 640.0 - u))
  assert len(observations) == 1
  assert len(observations[0].points) == 8
  assert observations[0].marking_type == LaneMarkingType.unknown
  assert 0.5 <= observations[0].confidence <= 1.0
