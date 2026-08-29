import numpy as np

from types import SimpleNamespace

from openpilot.sunnypilot.lane_topology.image_marking import classify_marking_continuity, measure_marking_continuity, \
                                                               project_model_lane_to_image
from openpilot.sunnypilot.lane_topology.types import LaneMarkingType


def test_luma_and_rgb_inputs_produce_same_solid_result():
  points = tuple((60.0, float(v)) for v in range(20, 101, 8))
  luma = np.full((120, 120), 30, dtype=np.uint8)
  luma[:, 58:63] = 240
  rgb = np.repeat(luma[:, :, None], 3, axis=2)
  assert classify_marking_continuity(luma, points) == LaneMarkingType.solid
  assert classify_marking_continuity(rgb, points) == LaneMarkingType.solid
  evidence = measure_marking_continuity(luma, points)
  assert evidence.sample_count > len(points)
  assert evidence.coverage == 1.0


def test_model_lane_projection_filters_distance_and_image_bounds():
  lane = SimpleNamespace(x=(1.0, 3.0, 10.0, 80.0), y=(0.0, 0.0, 0.0, 0.0), z=(1.0, 1.0, 1.0, 1.0))
  # u=x/z and v=y/z under this synthetic camera matrix.
  projected = project_model_lane_to_image(lane, np.eye(3), 20, 20)
  assert projected == ((3.0, 0.0), (10.0, 0.0))
