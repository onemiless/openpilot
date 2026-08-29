from __future__ import annotations

from collections.abc import Callable
import hashlib
from pathlib import Path

import numpy as np

from openpilot.sunnypilot.lane_topology.adapter import LaneTopologyFrame
from openpilot.sunnypilot.lane_topology.types import LaneBoundaryObservation
from openpilot.sunnypilot.lane_topology.yolop import HomographyProjector, lane_logits_to_observations, letterbox_rgb


EXPECTED_YOLOP_320_SHA256 = "86d6e8b6dfdef195c061e9bcad82d9487bb5ee1ac4a1cf9a3dc4736657a07369"
SUPPORTED_YOLOP_320_MODELS = {
  EXPECTED_YOLOP_320_SHA256: "official-full-fp32",
  "03690d106c5e59f8c6c55aa9a24b4bca795db1c7e1335887e26c50f43ee2feaf": "lane-only-fp32",
  "b7b09f3e918627b124943dcb7fa819b4c6968c7528f8eef9a474a082d4ef65ba": "lane-only-fp16",
}


class YOLOPOnnxLaneModel:
  """Lazy tinygrad ONNX runner using the caller's existing default device."""

  def __init__(self, model_path: str | Path):
    self.model_path = Path(model_path)
    if not self.model_path.is_file():
      raise FileNotFoundError(self.model_path)
    with self.model_path.open("rb") as model_file:
      observed_hash = hashlib.file_digest(model_file, "sha256").hexdigest()
    if observed_hash not in SUPPORTED_YOLOP_320_MODELS:
      raise RuntimeError(f"YOLOP 320 hash mismatch: {observed_hash}")
    self.model_sha256 = observed_hash
    self.variant = SUPPORTED_YOLOP_320_MODELS[observed_hash]

    # Imports are deliberately delayed: importing lane_topology never selects
    # a device or opens USB. modeld constructs this only after its primary AMD
    # device is ready, so both models share one owner and one tinygrad Device.
    from tinygrad import TinyJit
    from tinygrad.nn.onnx import OnnxRunner

    self._runner = OnnxRunner(self.model_path)
    self._forward = TinyJit(lambda images: self._runner({"images": images})["lane_line_seg"].contiguous(), prune=True)

  def lane_logits(self, rgb: np.ndarray) -> tuple[np.ndarray, object]:
    from tinygrad import Tensor

    input_array, transform = letterbox_rgb(rgb)
    output = self._forward(Tensor(input_array)).numpy()
    return output, transform

  def close(self) -> None:
    pass


class YOLOPLaneTopologyAdapter:
  """Convert a road RGB frame and image homography into lane observations."""

  def __init__(self, model: YOLOPOnnxLaneModel,
               projector_factory: Callable[[object], Callable[[float, float], tuple[float, float] | None]] | None = None):
    self.model = model
    self.projector_factory = projector_factory or (lambda calibration: HomographyProjector(np.asarray(calibration)))

  def infer(self, frame: LaneTopologyFrame) -> tuple[LaneBoundaryObservation, ...]:
    if not isinstance(frame.payload, np.ndarray):
      raise TypeError("YOLOP candidate expects an RGB numpy frame; VisionBuf conversion is a later production seam")
    if frame.calibration is None:
      raise ValueError("YOLOP candidate requires an image-to-vehicle homography")
    lane_logits, transform = self.model.lane_logits(frame.payload)
    return lane_logits_to_observations(lane_logits, transform, self.projector_factory(frame.calibration))

  def close(self) -> None:
    self.model.close()
