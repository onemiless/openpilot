import numpy as np
import pytest

from openpilot.sunnypilot.lane_topology.ufldv1 import decode_tusimple_v1, prepare_tusimple_v1_rgb


def test_v1_preprocess_contract():
  prepared = prepare_tusimple_v1_rgb(np.zeros((720, 1280, 3), dtype=np.uint8))
  assert prepared.shape == (1, 3, 288, 800)
  assert prepared.dtype == np.float32


def test_v1_decode_recovers_one_lane_in_source_pixels():
  logits = np.full((1, 101, 56, 4), -8.0, dtype=np.float32)
  logits[:, 49, -5:, 1] = 8.0
  logits[:, 100, :-5, 1] = 8.0
  logits[:, 100, :, (0, 2, 3)] = 8.0
  lanes = decode_tusimple_v1(logits, 1280, 720)
  assert len(lanes) == 1
  assert len(lanes[0]) == 5
  assert lanes[0][-1][0] == pytest.approx(50.0 * (799.0 / 99.0) * 1280.0 / 800.0 - 1.0, abs=0.05)
  assert lanes[0][-1][1] == pytest.approx(709.0, abs=0.01)


def test_v1_decode_rejects_wrong_shape():
  with pytest.raises(ValueError, match="output shape"):
    decode_tusimple_v1(np.zeros((1, 100, 56, 4), dtype=np.float32), 1280, 720)
