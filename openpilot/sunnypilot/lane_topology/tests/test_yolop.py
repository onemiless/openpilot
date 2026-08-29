import numpy as np
import pytest

from openpilot.sunnypilot.lane_topology.types import LaneMarkingType
from openpilot.sunnypilot.lane_topology.yolop import HomographyProjector, lane_logits_to_observations, letterbox_rgb


def test_letterbox_preserves_aspect_ratio_and_round_trips_source_coordinates():
  image = np.zeros((100, 200, 3), dtype=np.uint8)
  tensor, transform = letterbox_rgb(image)
  assert tensor.shape == (1, 3, 320, 320)
  assert transform.resized_width == 320
  assert transform.resized_height == 160
  assert transform.pad_y == 80
  assert transform.to_source(160, 160) == pytest.approx((100, 50))
  assert transform.to_source(160, 20) is None


def _synthetic_logits(*, dashed: bool) -> np.ndarray:
  logits = np.zeros((1, 2, 320, 320), dtype=np.float32)
  logits[:, 0] = 0.8
  for v in range(80, 320, 4):
    if dashed and (v // 16) % 2:
      continue
    for u in (120, 200):
      logits[0, 0, v, u - 1:u + 2] = 0.1
      logits[0, 1, v, u - 1:u + 2] = 0.9
  return logits


def _projector(u: float, v: float) -> tuple[float, float]:
  # Bottom of the image is near the car; pixels left of centre are positive y.
  return (max(0.0, (320.0 - v) * 0.2), (160.0 - u) * 0.045)


@pytest.mark.parametrize(("dashed", "expected_type"), (
  (False, LaneMarkingType.solid),
  (True, LaneMarkingType.dashed),
))
def test_lane_mask_becomes_two_vehicle_coordinate_instances(dashed: bool, expected_type: LaneMarkingType):
  image = np.zeros((320, 320, 3), dtype=np.uint8)
  _, transform = letterbox_rgb(image)
  observations = lane_logits_to_observations(_synthetic_logits(dashed=dashed), transform, _projector)
  assert len(observations) == 2
  assert {observation.marking_type for observation in observations} == {expected_type}
  assert observations[0].points[0][1] > 0
  assert observations[1].points[0][1] < 0


def test_homography_projector_uses_homogeneous_division():
  projector = HomographyProjector(np.array(((0.0, 0.1, 0.0), (-0.05, 0.0, 5.0), (0.0, 0.0, 1.0))))
  assert projector(120.0, 200.0) == pytest.approx((20.0, -1.0))
