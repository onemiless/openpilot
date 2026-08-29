from __future__ import annotations

from collections.abc import Callable
import hashlib
from pathlib import Path

import numpy as np

from openpilot.sunnypilot.lane_topology.adapter import LaneTopologyFrame
from openpilot.sunnypilot.lane_topology.types import LaneBoundaryObservation
from openpilot.sunnypilot.lane_topology.ufldv1 import prepare_tusimple_v1_rgb, v1_logits_to_observations
from openpilot.sunnypilot.lane_topology.yolop import HomographyProjector


EXPECTED_UFLDV1_TUSIMPLE_RES18_SHA256 = "46a1864bcc8c13497fe0c18d4584fed993482d5170d3152ef5e138ff1e471b2d"


class UFLDv1OnnxLaneModel:
  """Official UFLDv1 ResNet18, lazily attached to the selected tinygrad device."""

  def __init__(self, model_path: str | Path):
    self.model_path = Path(model_path)
    if not self.model_path.is_file():
      raise FileNotFoundError(self.model_path)
    with self.model_path.open("rb") as model_file:
      self.model_sha256 = hashlib.file_digest(model_file, "sha256").hexdigest()
    if self.model_sha256 != EXPECTED_UFLDV1_TUSIMPLE_RES18_SHA256:
      raise RuntimeError(f"UFLDv1 TuSimple ResNet18 hash mismatch: {self.model_sha256}")

    from tinygrad import TinyJit
    from tinygrad.nn.onnx import OnnxRunner

    self._runner = OnnxRunner(self.model_path)
    self._forward = TinyJit(lambda images: self._runner({"images": images})["lane_logits"].contiguous(), prune=True)

  def logits(self, rgb: np.ndarray) -> np.ndarray:
    from tinygrad import Tensor

    return self._forward(Tensor(prepare_tusimple_v1_rgb(rgb))).numpy()

  def close(self) -> None:
    pass


class UFLDv1LaneTopologyAdapter:
  def __init__(self, model: UFLDv1OnnxLaneModel,
               projector_factory: Callable[[object], Callable[[float, float], tuple[float, float] | None]] | None = None):
    self.model = model
    self.projector_factory = projector_factory or (lambda calibration: HomographyProjector(np.asarray(calibration)))

  def infer(self, frame: LaneTopologyFrame) -> tuple[LaneBoundaryObservation, ...]:
    if not isinstance(frame.payload, np.ndarray):
      raise TypeError("UFLDv1 candidate expects an RGB numpy frame; VisionBuf conversion is a later production seam")
    if frame.calibration is None:
      raise ValueError("UFLDv1 candidate requires an image-to-vehicle homography")
    return v1_logits_to_observations(self.model.logits(frame.payload), frame.payload, self.projector_factory(frame.calibration))

  def close(self) -> None:
    self.model.close()
